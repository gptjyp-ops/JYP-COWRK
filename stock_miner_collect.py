from __future__ import annotations

import json
import os
import math
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from kiwoom import get_client, KiwoomError
from stock_miner_watchlist import include_watchlist
from stock_miner_observations import include_pending

OUT = Path("stock-miner-data.json")
REQUEST_DELAY = 0.22
SOURCE_LIMIT = 120  # 각 경로에서 필터를 통과한 고유 종목 수
MAX_SOURCE_PAGES = 20  # API 호출의 상한; 목표 개수를 보장하지는 않음
MAX_CANDIDATES = 300
SOURCE_DIAGNOSTICS = {}
STOCK_DIAGNOSTICS = {}
KST = timezone(timedelta(hours=9))
MIN_PRICE = 500
MAX_ABS_CHANGE = 20.0

ETF_PREFIXES = (
    "KODEX", "TIGER", "ACE", "RISE", "ARIRANG", "SOL ", "KOSEF",
    "HANARO", "TIMEFOLIO", "히어로즈", "PLUS ", "FOCUS", "WOORI ",
)
EXCLUDE_WORDS = ("리츠", "스팩", "ETN", "(Reg.S)")


def num(v, default=0.0):
    if v is None:
        return default
    s = str(v).strip().replace(",", "").replace("+", "")
    try:
        return float(s)
    except Exception:
        return default


def required_num(value, field):
    if value is None or str(value).strip() in ("", "-", "--"):
        raise RuntimeError(f"필수 숫자 누락: {field}")
    try:
        number = float(str(value).strip().replace(",", "").replace("+", ""))
    except (ValueError, TypeError):
        raise RuntimeError(f"필수 숫자 형식 오류: {field}") from None
    if not math.isfinite(number):
        raise RuntimeError(f"유효하지 않은 숫자: {field}")
    return number


def dated_rows(rows, minimum, label):
    unique = {}
    today = datetime.now(KST).strftime("%Y%m%d")
    for row in rows:
        date = str(row.get("dt", ""))
        try:
            datetime.strptime(date, "%Y%m%d")
        except ValueError:
            raise RuntimeError(f"{label} 일자 누락 또는 형식 오류") from None
        if date > today:
            raise RuntimeError(f"{label} 미래 일자 응답")
        if date in unique and unique[date] != row:
            raise RuntimeError(f"{label} 동일 일자 상충 데이터")
        unique[date] = row
    result = [unique[date] for date in sorted(unique, reverse=True)]
    if len(result) < minimum:
        raise RuntimeError(f"{label} 고유 일자 {minimum}개 미만")
    return result


def fetch(api_id: str, path: str, body: dict, want_key: str, max_pages: int = 1, max_rows: int | None = None):
    client = get_client()
    rows = []
    cont_yn = None
    next_key = None
    for _ in range(max_pages):
        res = client.fetch_page(api_id=api_id, path=path, body=body, cont_yn=cont_yn, next_key=next_key)
        rb = res.body
        if rb.get("return_code") not in (None, 0):
            raise RuntimeError(f"{api_id}: {rb.get('return_msg') or rb.get('return_code')}")
        recs = rb.get(want_key)
        if not isinstance(recs, list) or any(not isinstance(x, dict) for x in recs):
            raise RuntimeError(f"{api_id}: 응답 목록 형식 오류 ({want_key})")
        rows.extend(recs)
        if max_rows and len(rows) >= max_rows:
            break
        cont_yn = res.continuation.cont_yn
        next_key = res.continuation.next_key
        if cont_yn != "Y":
            break
        time.sleep(REQUEST_DELAY)
    return rows[:max_rows] if max_rows else rows


def prefilter_reason(code: str, name: str) -> str | None:
    if not (len(code) == 6 and code.isdigit()):
        return "일반주식 코드 아님"
    if any(name.startswith(p) for p in ETF_PREFIXES):
        return "ETF/펀드"
    if any(w in name for w in EXCLUDE_WORDS):
        return "리츠/스팩/ETN/해외특수상장"
    if name.endswith("우") or name.endswith("우B") or name.endswith("우C"):
        return "우선주"
    return None


def add_candidate(pool: dict, filtered: list, code: str, name: str, source: str, **extra):
    code = str(code or "").strip()
    name = str(name or "").strip()
    if not code or not name:
        return
    reason = prefilter_reason(code, name)
    if reason:
        filtered.append({"code": code, "name": name, "reason": reason, "source": source})
        return
    if code not in pool:
        pool[code] = {
            "code": code,
            "name": name,
            "sources": [],
            "foreign_streak_total": 0,
            "institution_rank_qty": 0,
            "volume_rank_qty": 0,
        }
    item = pool[code]
    if source not in item["sources"]:
        item["sources"].append(source)
    for k, v in extra.items():
        if v is not None:
            item[k] = v


def collect_ranked(pool, filtered, source, code_key, name_key, extras,
                   api_id, path, body, want_key, change_key=None):
    """필터 통과 종목을 확보할 때까지 연속 조회하며 원본 행 누락을 진단한다."""
    client = get_client()
    accepted, seen_tokens = set(), set()
    cont_yn = next_key = None
    diag = {"pages": 0, "raw_rows": 0, "accepted": 0,
            "excluded": 0, "missing_identity": 0, "duplicates": 0,
            "row_fields": [], "stop_reason": "page_limit"}
    SOURCE_DIAGNOSTICS[source] = diag
    for _ in range(MAX_SOURCE_PAGES):
        res = client.fetch_page(api_id=api_id, path=path, body=body,
                                cont_yn=cont_yn, next_key=next_key)
        rb = res.body
        diag["pages"] += 1
        if rb.get("return_code") not in (None, 0):
            raise RuntimeError(f"{api_id}: {rb.get('return_msg') or rb.get('return_code')}")
        if not isinstance(rb.get(want_key), list):
            diag["stop_reason"] = "response_schema_mismatch"
            diag["response_fields"] = sorted(rb.keys())
            break
        rows = rb[want_key]
        diag["raw_rows"] += len(rows)
        for r in rows:
            if not isinstance(r, dict):
                diag["missing_identity"] += 1
                continue
            if not diag["row_fields"]:
                diag["row_fields"] = sorted(r.keys())
            code = str(r.get(code_key) or "").strip()
            name = str(r.get(name_key) or "").strip()
            if not code or not name:
                diag["missing_identity"] += 1
                continue
            reason = prefilter_reason(code, name)
            if change_key and abs(num(r.get(change_key))) > MAX_ABS_CHANGE:
                reason = f"당일 변동 {MAX_ABS_CHANGE:.0f}% 초과"
            if reason:
                diag["excluded"] += 1
                filtered.append({"code": code, "name": name, "reason": reason, "source": source})
                continue
            if code in accepted:
                diag["duplicates"] += 1
                continue
            accepted.add(code)
            add_candidate(pool, filtered, code, name, source,
                          **{k: num(r.get(v)) for k, v in extras.items()})
            if len(accepted) >= SOURCE_LIMIT:
                break
        diag["accepted"] = len(accepted)
        if len(accepted) >= SOURCE_LIMIT:
            diag["stop_reason"] = "target_reached"
            break
        cont_yn = res.continuation.cont_yn
        next_key = res.continuation.next_key
        if cont_yn != "Y":
            diag["stop_reason"] = "source_exhausted"
            break
        if not next_key or next_key in seen_tokens:
            diag["stop_reason"] = "invalid_continuation"
            break
        seen_tokens.add(next_key)
        time.sleep(REQUEST_DELAY)
    print(f"[후보진단] {source}: 원본 {diag['raw_rows']}행 / 확보 {diag['accepted']} / "
          f"제외 {diag['excluded']} / 코드·이름누락 {diag['missing_identity']} / "
          f"{diag['pages']}페이지 / {diag['stop_reason']}")
    if diag["missing_identity"] or diag["stop_reason"] == "response_schema_mismatch":
        print(f"[후보경고] {source} 응답 필드 확인 필요: "
              f"{diag.get('response_fields', diag['row_fields'])}")


def select_candidates(pool):
    """복수 포착을 우선하고 단일 경로는 순위 순으로 번갈아 선택한다."""
    items = list(pool.values())
    multi = sorted((x for x in items if len(x['sources']) > 1),
                   key=lambda x: len(x['sources']), reverse=True)
    selected = multi[:MAX_CANDIDATES]
    queues = [[x for x in items if x['sources'] == [source]]
              for source in ('외국인연속', '기관순매수', '거래량상위')]
    for rank in range(max((len(q) for q in queues), default=0)):
        for queue in queues:
            if len(selected) >= MAX_CANDIDATES:
                return selected
            if rank < len(queue):
                selected.append(queue[rank])
    return selected


def collect_foreign_streak(pool: dict, filtered: list):
    collect_ranked(
        pool, filtered, "외국인연속", "stk_cd", "stk_nm", {"foreign_streak_total": "tot"},
        "ka10035", "/api/dostk/rkinfo",
        {"mrkt_tp": "000", "trde_tp": "2", "base_dt_tp": "0", "stex_tp": "1"},
        "for_cont_nettrde_upper",
    )


def collect_institution_top(pool: dict, filtered: list):
    today = datetime.now(KST).strftime("%Y%m%d")
    collect_ranked(
        pool, filtered, "기관순매수", "orgn_netprps_stk_cd", "orgn_netprps_stk_nm",
        {"institution_rank_qty": "orgn_netprps_qty"},
        "ka90009", "/api/dostk/rkinfo",
        {"mrkt_tp": "000", "amt_qty_tp": "2", "qry_dt_tp": "1", "stex_tp": "1", "date": today},
        "frgnr_orgn_trde_upper",
    )


def collect_volume_top(pool: dict, filtered: list):
    collect_ranked(
        pool, filtered, "거래량상위", "stk_cd", "stk_nm", {"volume_rank_qty": "trde_qty"},
        "ka10030", "/api/dostk/rkinfo",
        {
            "mrkt_tp": "000", "sort_tp": "1", "mang_stk_incls": "16",
            "crd_tp": "0", "trde_qty_tp": "0", "pric_tp": "0",
            "trde_prica_tp": "0", "mrkt_open_tp": "0", "stex_tp": "1",
        },
        "tdy_trde_qty_upper", change_key="flu_rt",
    )


def collect_candidates():
    SOURCE_DIAGNOSTICS.clear()
    STOCK_DIAGNOSTICS.clear()
    pool, filtered = {}, []
    collect_foreign_streak(pool, filtered)
    time.sleep(REQUEST_DELAY)
    collect_institution_top(pool, filtered)
    time.sleep(REQUEST_DELAY)
    collect_volume_top(pool, filtered)

    ranked_candidates = select_candidates(pool)
    candidates = include_pending(include_watchlist(ranked_candidates))
    print(f"[범위] 통합 {len(pool)}개 / 상세분석 {len(candidates)}개 / "
          f"분석한도 제외 {len(pool) - len(ranked_candidates)}개")
    return candidates, filtered


def investor_5d(code: str):
    today = datetime.now(KST).strftime("%Y%m%d")
    rows = fetch("ka10059", "/api/dostk/stkinfo",
        {"dt": today, "stk_cd": code, "amt_qty_tp": "2", "trde_tp": "0", "unit_tp": "1"},
        "stk_invsr_orgn", max_pages=2, max_rows=10)
    rows = dated_rows(rows, 5, "수급")[:5]
    sample = [{"date": r["dt"],
               "foreign": required_num(r.get("frgnr_invsr"), "frgnr_invsr"),
               "institution": required_num(r.get("orgn"), "orgn"),
               "individual": required_num(r.get("ind_invsr"), "ind_invsr")} for r in rows]
    STOCK_DIAGNOSTICS.setdefault(code, {})["investor"] = {"unit": "shares", "rows": sample}
    return tuple(sum(r[key] for r in sample) for key in ("foreign", "institution", "individual"))


def chart_metrics(code: str):
    today = datetime.now(KST).strftime("%Y%m%d")
    rows = fetch("ka10081", "/api/dostk/chart",
        {"stk_cd": code, "base_dt": today, "upd_stkpc_tp": "1"},
        "stk_dt_pole_chart_qry", max_pages=3, max_rows=70)
    rows = dated_rows(rows, 60, "일봉")[:60]
    prices = [abs(required_num(r.get("cur_prc"), "cur_prc")) for r in rows]
    vols = [required_num(r.get("trde_qty"), "trde_qty") for r in rows]
    if any(price <= 0 for price in prices) or any(volume < 0 for volume in vols):
        raise RuntimeError("차트 가격 또는 거래량 범위 오류")
    current = prices[0]
    ma20, ma60 = sum(prices[:20]) / 20, sum(prices[:60]) / 60
    avg20vol = sum(vols[1:21]) / 20
    if avg20vol <= 0:
        raise RuntimeError("과거 20일 평균 거래량 0 이하")
    metrics = (current, (current / prices[1] - 1) * 100, vols[0] / avg20vol,
               (current / ma20 - 1) * 100, (current / ma60 - 1) * 100)
    STOCK_DIAGNOSTICS.setdefault(code, {})["chart"] = {
        "adjusted_prices": True, "exchange": "KRX",
        "volume_basis": "intraday_cumulative_vs_previous_20_full_days",
        "rows": [{"date": r["dt"], "price": price, "volume": volume} for r, price, volume in zip(rows, prices, vols)],
        "ma20": ma20, "ma60": ma60, "previous_20_average_volume": avg20vol,
    }
    return metrics


def postfilter_reason(price: float, change: float, vol_ratio: float) -> str | None:
    if price < MIN_PRICE:
        return f"{MIN_PRICE}원 미만"
    if abs(change) > MAX_ABS_CHANGE:
        return f"당일 변동 {MAX_ABS_CHANGE:.0f}% 초과"
    if vol_ratio <= 0:
        return "거래량 데이터 이상"
    return None


def local_score(f5, i5, vol_ratio, dist20, dist60, streak_total, sources):
    score = 0.0

    # 수급 40점
    score += 20 if f5 > 0 else 0
    score += 10 if i5 > 0 else 0
    score += 10 if streak_total > 0 else 0

    # 거래량 15점
    if vol_ratio >= 3:
        score += 15
    elif vol_ratio >= 2:
        score += 12
    elif vol_ratio >= 1.5:
        score += 8
    elif vol_ratio >= 1.2:
        score += 4

    # 차트 위치 25점
    d20, d60 = abs(dist20), abs(dist60)
    score += max(0, 12.5 - min(d20, 15) / 15 * 12.5)
    score += max(0, 12.5 - min(d60, 25) / 25 * 12.5)

    # 초기 추세 15점
    if -5 <= dist20 <= 8:
        score += 7.5
    if -8 <= dist60 <= 12:
        score += 7.5

    # 복수 입구 포착 보너스 5점
    if len(sources) >= 3:
        score += 5
    elif len(sources) == 2:
        score += 3

    # 이미 많이 벌어진 종목 감점
    if dist20 > 15:
        score -= 8
    if dist60 > 30:
        score -= 5

    return round(max(0, min(score, 100)), 1)


def main():
    started = datetime.now(KST).isoformat(timespec="seconds")
    print("[1/4] 외국인 연속순매수 후보")
    print("[2/4] 기관 순매수 상위 후보")
    print("[3/4] 거래량 상위 후보")
    candidates, filtered = collect_candidates()
    print(f"3개 소스 통합 후 중복제거 후보 {len(candidates)}개")

    result = []
    total = len(candidates)
    for idx, c in enumerate(candidates, 1):
        code, name = c["code"], c["name"]
        src = "+".join(c.get("sources", []))
        print(f"[{idx}/{total}] {name} {code} [{src}]")
        try:
            f5, i5, p5 = investor_5d(code)
            time.sleep(REQUEST_DELAY)
            price, change, vr, d20, d60 = chart_metrics(code)
            reason = postfilter_reason(price, change, vr)
            if reason and not (c.get("fixed_watch") or c.get("comparison_only")):
                filtered.append({"code": code, "name": name, "reason": reason, "source": src})
                continue

            score = local_score(f5, i5, vr, d20, d60, c.get("foreign_streak_total", 0), c.get("sources", []))
            stage = "집중관찰" if score >= 80 else "관찰" if score >= 70 else "대기"
            reasons = []
            if c.get("fixed_watch"): reasons.append("고정 관심종목 추적")
            if reason: reasons.append("발굴 필터 참고: " + reason)
            if "외국인연속" in c.get("sources", []): reasons.append("외국인 연속순매수 상위 포착")
            if "기관순매수" in c.get("sources", []): reasons.append("기관 순매수 상위 포착")
            if "거래량상위" in c.get("sources", []): reasons.append("거래량 상위 포착")
            if f5 > 0: reasons.append("외국인 5일 순매수")
            if i5 > 0: reasons.append("기관 5일 순매수")
            if vr >= 1.5: reasons.append(f"20일 평균 대비 거래량 {vr:.1f}배")
            if abs(d20) <= 5 or abs(d60) <= 5: reasons.append("20일 또는 60일 이평선 근처")

            result.append({
                "code": code,
                "name": name,
                "stage": stage,
                "score_base": score,
                "sources": c.get("sources", []),
                "source_count": len(c.get("sources", [])),
                "fixed_watch": bool(c.get("fixed_watch")),
                "comparison_only": bool(c.get("comparison_only")),
                "screening_note": reason,
                "price": round(price),
                "change": round(change, 2),
                "foreign5": round(f5),
                "inst5": round(i5),
                "personal5": round(p5),
                "foreign_streak_total": round(c.get("foreign_streak_total", 0)),
                "institution_rank_qty": round(c.get("institution_rank_qty", 0)),
                "volume_rank_qty": round(c.get("volume_rank_qty", 0)),
                "vol_ratio": round(vr, 2),
                "dist20": round(d20, 2),
                "dist60": round(d60, 2),
                "reasons": reasons,
                "op_yoy": None,
                "disclosure": "DART 대기",
                "theme": "분류 전",
                "market_data_status": "input_checked",
                "quote_date": STOCK_DIAGNOSTICS[code]["chart"]["rows"][0]["date"],
                "investor_dates": [r["date"] for r in STOCK_DIAGNOSTICS[code]["investor"]["rows"]],
                "collected_at": datetime.now(KST).isoformat(timespec="seconds"),
                "volume_basis": "intraday_cumulative_vs_previous_20_full_days",
            })
        except Exception as e:
            result.append({"code": code, "name": name, "sources": c.get("sources", []), "error": str(e)})
        time.sleep(REQUEST_DELAY)

    good = [r for r in result if "error" not in r]
    good.sort(key=lambda x: (x.get("score_base", 0), x.get("source_count", 0)), reverse=True)
    dart_ready = bool(os.getenv("DART_API_KEY"))
    source_counts = {
        "foreign": sum("외국인연속" in r.get("sources", []) for r in good),
        "institution": sum("기관순매수" in r.get("sources", []) for r in good),
        "volume": sum("거래량상위" in r.get("sources", []) for r in good),
        "multi_source": sum(r.get("source_count", 0) >= 2 for r in good),
    }
    payload = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "version": "stock-miner-collector-v3",
        "note": "외국인 연속순매수 + 기관 순매수 상위 + 거래량 상위 3개 입구를 통합한 뒤, 5일 수급·20일 거래량배수·20/60일선으로 점수화. DART 실적/공시는 아직 미합산.",
        "count": len(good),
        "filtered_count": len(filtered),
        "source_counts": source_counts,
        "collector_revision": "validated-inputs-2",
        "collection_started_at": started,
        "data_quality": {"status": "needs_review" if any(d["accepted"] == 0 or d["missing_identity"] or d["stop_reason"] == "response_schema_mismatch" for d in SOURCE_DIAGNOSTICS.values()) else "ok",
            "empty_sources": [k for k, d in SOURCE_DIAGNOSTICS.items() if d["accepted"] == 0]},
        "market_audit": {code: STOCK_DIAGNOSTICS[code] for code in (r["code"] for r in good)},
        "source_diagnostics": SOURCE_DIAGNOSTICS,
        "collection_limits": {"accepted_per_source": SOURCE_LIMIT,
                              "pages_per_source": MAX_SOURCE_PAGES,
                              "detail_candidates": MAX_CANDIDATES},
        "filters": {
            "common_stock_only": True,
            "min_price": MIN_PRICE,
            "max_abs_daily_change": MAX_ABS_CHANGE,
            "require_60_daily_bars": True,
            "exclude_etf_etn_reit_spac_preferred_reg_s": True,
        },
        "dart": {"api_key_detected": dart_ready, "status": "연결 준비" if dart_ready else "API 키 필요"},
        "stocks": good,
        "filtered": filtered,
        "errors": [r for r in result if "error" in r],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[완료] {OUT.resolve()}")
    print(f"통과 {len(good)}개 / 필터 제외 {len(filtered)}개 / 오류 {len(payload['errors'])}개")
    print(f"외국인 {source_counts['foreign']} / 기관 {source_counts['institution']} / 거래량 {source_counts['volume']} / 복수포착 {source_counts['multi_source']}")
    print("상위 10개:")
    for r in good[:10]:
        src = "+".join(r.get("sources", []))
        print(f"{r['score_base']:>5}  {r['name']:<16} {r['code']} [{src}] 외5 {r['foreign5']:+,.0f} 기관5 {r['inst5']:+,.0f} 거래량 {r['vol_ratio']:.2f}x")


if __name__ == "__main__":
    try:
        main()
    except KiwoomError as e:
        raise SystemExit(f"키움 API 오류: {e}")


