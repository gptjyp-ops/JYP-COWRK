from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

from kiwoom import get_client, KiwoomError

OUT = Path("stock-miner-data.json")
CANDIDATE_LIMIT = 80
REQUEST_DELAY = 0.22
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
        recs = rb.get(want_key, [])
        if isinstance(recs, list):
            rows.extend(x for x in recs if isinstance(x, dict))
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
    # 단순 우선주 필터. 일반주 중 이름이 실제로 '우'로 끝나는 예외는 매우 드뭅니다.
    if name.endswith("우") or name.endswith("우B") or name.endswith("우C"):
        return "우선주"
    return None


def foreign_streak_candidates():
    rows = fetch(
        "ka10035", "/api/dostk/rkinfo",
        {"mrkt_tp": "000", "trde_tp": "2", "base_dt_tp": "0", "stex_tp": "1"},
        "for_cont_nettrde_upper", max_pages=5, max_rows=CANDIDATE_LIMIT,
    )
    out, filtered = [], []
    for r in rows:
        code = str(r.get("stk_cd", "")).strip()
        name = str(r.get("stk_nm", "")).strip()
        if not code or not name:
            continue
        reason = prefilter_reason(code, name)
        if reason:
            filtered.append({"code": code, "name": name, "reason": reason})
            continue
        out.append({
            "code": code,
            "name": name,
            "foreign_streak_total": num(r.get("tot")),
            "foreign_d1": num(r.get("dm1")),
            "foreign_d2": num(r.get("dm2")),
            "foreign_d3": num(r.get("dm3")),
        })
    return out, filtered


def investor_5d(code: str):
    today = datetime.now().strftime("%Y%m%d")
    rows = fetch(
        "ka10059", "/api/dostk/stkinfo",
        {"dt": today, "stk_cd": code, "amt_qty_tp": "2", "trde_tp": "0", "unit_tp": "1"},
        "stk_invsr_orgn", max_pages=2, max_rows=5,
    )
    return (
        sum(num(r.get("frgnr_invsr")) for r in rows[:5]),
        sum(num(r.get("orgn")) for r in rows[:5]),
        sum(num(r.get("ind_invsr")) for r in rows[:5]),
    )


def chart_metrics(code: str):
    today = datetime.now().strftime("%Y%m%d")
    rows = fetch(
        "ka10081", "/api/dostk/chart",
        {"stk_cd": code, "base_dt": today, "upd_stkpc_tp": "1"},
        "stk_dt_pole_chart_qry", max_pages=3, max_rows=70,
    )
    if len(rows) < 60:
        raise RuntimeError("일봉 60개 미만")

    prices = [abs(num(r.get("cur_prc"))) for r in rows if num(r.get("cur_prc")) != 0]
    vols = [abs(num(r.get("trde_qty"))) for r in rows if num(r.get("trde_qty")) >= 0]
    if len(prices) < 60 or len(vols) < 21:
        raise RuntimeError("차트 데이터 부족")

    current = prices[0]
    ma20 = sum(prices[:20]) / 20
    ma60 = sum(prices[:60]) / 60
    prev20 = vols[1:21]
    avg20vol = sum(prev20) / 20 if prev20 else 0
    vol_ratio = (vols[0] / avg20vol) if avg20vol else 0
    dist20 = ((current / ma20) - 1) * 100 if ma20 else 0
    dist60 = ((current / ma60) - 1) * 100 if ma60 else 0
    change = (current / prices[1] - 1) * 100 if prices[1] else 0
    return current, change, vol_ratio, dist20, dist60


def postfilter_reason(price: float, change: float, vol_ratio: float) -> str | None:
    if price < MIN_PRICE:
        return f"{MIN_PRICE}원 미만"
    if abs(change) > MAX_ABS_CHANGE:
        return f"당일 변동 {MAX_ABS_CHANGE:.0f}% 초과"
    if vol_ratio <= 0:
        return "거래량 데이터 이상"
    return None


def local_score(f5, i5, vol_ratio, dist20, dist60, streak_total):
    score = 0.0
    score += 20 if f5 > 0 else 0
    score += 10 if i5 > 0 else 0
    score += 10 if streak_total > 0 else 0
    if vol_ratio >= 3:
        score += 15
    elif vol_ratio >= 2:
        score += 12
    elif vol_ratio >= 1.5:
        score += 8
    elif vol_ratio >= 1.2:
        score += 4

    d20, d60 = abs(dist20), abs(dist60)
    score += max(0, 12.5 - min(d20, 15) / 15 * 12.5)
    score += max(0, 12.5 - min(d60, 25) / 25 * 12.5)
    if -5 <= dist20 <= 8:
        score += 10
    if -8 <= dist60 <= 12:
        score += 10
    if dist20 > 15:
        score -= 8
    return round(max(0, min(score, 100)), 1)


def main():
    print("[1/3] 외국인 연속순매수 후보 수집 + 일반주 필터")
    candidates, filtered = foreign_streak_candidates()
    print(f"원천 후보 최대 {CANDIDATE_LIMIT}개 / 사전필터 후 {len(candidates)}개")

    result = []
    total = len(candidates)
    for idx, c in enumerate(candidates, 1):
        code, name = c["code"], c["name"]
        print(f"[{idx}/{total}] {name} {code}")
        try:
            f5, i5, p5 = investor_5d(code)
            time.sleep(REQUEST_DELAY)
            price, change, vr, d20, d60 = chart_metrics(code)
            reason = postfilter_reason(price, change, vr)
            if reason:
                filtered.append({"code": code, "name": name, "reason": reason})
                continue

            score = local_score(f5, i5, vr, d20, d60, c["foreign_streak_total"])
            stage = "집중관찰" if score >= 80 else "관찰" if score >= 70 else "대기"
            reasons = []
            if f5 > 0: reasons.append("외국인 5일 순매수")
            if i5 > 0: reasons.append("기관 5일 순매수")
            if vr >= 1.5: reasons.append(f"거래량 {vr:.1f}배")
            if abs(d20) <= 5 or abs(d60) <= 5: reasons.append("이평선/저점 접근")

            result.append({
                "code": code,
                "name": name,
                "stage": stage,
                "score_base": score,
                "price": round(price),
                "change": round(change, 2),
                "foreign5": round(f5),
                "inst5": round(i5),
                "personal5": round(p5),
                "foreign_streak_total": round(c["foreign_streak_total"]),
                "vol_ratio": round(vr, 2),
                "dist20": round(d20, 2),
                "dist60": round(d60, 2),
                "reasons": reasons,
                "op_yoy": None,
                "disclosure": "DART 대기",
                "theme": "분류 전",
            })
        except Exception as e:
            result.append({"code": code, "name": name, "error": str(e)})
        time.sleep(REQUEST_DELAY)

    good = [r for r in result if "error" not in r]
    good.sort(key=lambda x: x.get("score_base", 0), reverse=True)
    dart_ready = bool(os.getenv("DART_API_KEY"))
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "version": "stock-miner-collector-v2",
        "note": "일반 국내 개별주 필터 적용. 점수는 키움 수급·거래량·차트 기반이며 DART 실적/공시는 아직 미합산.",
        "count": len(good),
        "filtered_count": len(filtered),
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
    print("상위 10개:")
    for r in good[:10]:
        print(f"{r['score_base']:>5}  {r['name']:<16} {r['code']}  외5 {r['foreign5']:+,.0f}  기관5 {r['inst5']:+,.0f}  거래량 {r['vol_ratio']:.2f}x")


if __name__ == "__main__":
    try:
        main()
    except KiwoomError as e:
        raise SystemExit(f"키움 API 오류: {e}")
