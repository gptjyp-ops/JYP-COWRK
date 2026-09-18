from __future__ import annotations

import io
import json
import os
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

import requests

DATA_PATH = Path("stock-miner-data.json")
DART_BASE = "https://opendart.fss.or.kr/api"
REQUEST_DELAY = 0.12
LOOKBACK_DAYS = 90

POSITIVE_KEYWORDS = (
    "단일판매ㆍ공급계약", "단일판매·공급계약", "공급계약", "수주",
    "신규시설투자", "시설투자", "증설", "기술이전", "특허",
)
RISK_KEYWORDS = (
    "유상증자", "전환사채권발행", "전환사채 발행", "신주인수권부사채권발행",
    "신주인수권부사채 발행", "교환사채권발행", "교환사채 발행",
    "감자결정", "감자 결정", "최대주주변경", "최대주주 변경",
)


def n(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def get_json(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, dict) else {}


def load_corp_map(api_key: str) -> dict[str, str]:
    r = requests.get(f"{DART_BASE}/corpCode.xml", params={"crtfc_key": api_key}, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        xml_name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
        if not xml_name:
            raise RuntimeError("DART corpCode ZIP에 XML이 없습니다.")
        root = ET.fromstring(zf.read(xml_name))
    out = {}
    for item in root.findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        corp_code = (item.findtext("corp_code") or "").strip()
        if stock_code and corp_code:
            out[stock_code] = corp_code
    return out


def report_candidates(now: datetime):
    y = now.year
    # 아직 제출되지 않은 보고서는 013으로 넘어가고 다음 후보를 시도합니다.
    return [
        (str(y), "11014", "3분기"),
        (str(y), "11012", "반기"),
        (str(y), "11013", "1분기"),
        (str(y - 1), "11011", "사업보고서"),
    ]


def find_account(rows: list[dict], names: tuple[str, ...], ids: tuple[str, ...] = ()) -> dict | None:
    for r in rows:
        aid = str(r.get("account_id", ""))
        anm = str(r.get("account_nm", "")).replace(" ", "")
        if aid in ids or any(k.replace(" ", "") in anm for k in names):
            return r
    return None


def financials(api_key: str, corp_code: str) -> dict:
    now = datetime.now()
    for year, reprt_code, label in report_candidates(now):
        for fs_div in ("CFS", "OFS"):
            data = get_json(
                f"{DART_BASE}/fnlttSinglAcntAll.json",
                {
                    "crtfc_key": api_key,
                    "corp_code": corp_code,
                    "bsns_year": year,
                    "reprt_code": reprt_code,
                    "fs_div": fs_div,
                },
            )
            status = str(data.get("status", ""))
            if status == "013":
                continue
            if status != "000":
                continue
            rows = data.get("list") or []
            op = find_account(
                rows,
                ("영업이익", "영업손익"),
                ("ifrs-full_ProfitLossFromOperatingActivities",),
            )
            rev = find_account(
                rows,
                ("매출액", "영업수익", "수익(매출액)"),
                ("ifrs-full_Revenue",),
            )
            if not op:
                continue

            is_annual = reprt_code == "11011"
            cur_op = n(op.get("thstrm_amount") if is_annual else op.get("thstrm_add_amount"))
            prev_op = n(op.get("frmtrm_amount") if is_annual else op.get("frmtrm_add_amount"))
            cur_rev = n((rev or {}).get("thstrm_amount") if is_annual else (rev or {}).get("thstrm_add_amount"))
            prev_rev = n((rev or {}).get("frmtrm_amount") if is_annual else (rev or {}).get("frmtrm_add_amount"))

            turnaround = cur_op is not None and prev_op is not None and cur_op > 0 >= prev_op
            op_yoy = None
            if cur_op is not None and prev_op not in (None, 0):
                op_yoy = (cur_op - prev_op) / abs(prev_op) * 100
            rev_yoy = None
            if cur_rev is not None and prev_rev not in (None, 0):
                rev_yoy = (cur_rev - prev_rev) / abs(prev_rev) * 100
            op_margin = None
            if cur_op is not None and cur_rev not in (None, 0):
                op_margin = cur_op / cur_rev * 100

            if turnaround:
                fin_score = 15.0
            elif cur_op is None or cur_op <= 0:
                fin_score = 0.0
            elif op_yoy is None:
                fin_score = 7.0
            elif op_yoy >= 100:
                fin_score = 15.0
            elif op_yoy >= 30:
                fin_score = 13.0
            elif op_yoy > 0:
                fin_score = 10.0
            else:
                fin_score = 5.0

            return {
                "report_year": int(year),
                "report_code": reprt_code,
                "report_label": label,
                "fs_div": fs_div,
                "op_yoy": round(op_yoy, 2) if op_yoy is not None else None,
                "rev_yoy": round(rev_yoy, 2) if rev_yoy is not None else None,
                "op_margin": round(op_margin, 2) if op_margin is not None else None,
                "turnaround": bool(turnaround),
                "financial_score": fin_score,
            }
    return {
        "report_year": None,
        "report_code": None,
        "report_label": None,
        "fs_div": None,
        "op_yoy": None,
        "rev_yoy": None,
        "op_margin": None,
        "turnaround": False,
        "financial_score": 0.0,
    }


def disclosures(api_key: str, corp_code: str) -> dict:
    end = datetime.now().date()
    begin = end - timedelta(days=LOOKBACK_DAYS)
    data = get_json(
        f"{DART_BASE}/list.json",
        {
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bgn_de": begin.strftime("%Y%m%d"),
            "end_de": end.strftime("%Y%m%d"),
            "last_reprt_at": "Y",
            "sort": "date",
            "sort_mth": "desc",
            "page_count": "100",
        },
    )
    if str(data.get("status")) == "013":
        return {"positive": [], "risk": [], "latest": [], "disclosure_score": 0.0, "risk_penalty": 0.0}
    if str(data.get("status")) != "000":
        return {"positive": [], "risk": [], "latest": [], "disclosure_score": 0.0, "risk_penalty": 0.0}

    rows = data.get("list") or []
    positive, risk, latest = [], [], []
    for r in rows[:20]:
        title = str(r.get("report_nm", "")).strip()
        item = {
            "title": title,
            "date": r.get("rcept_dt"),
            "rcept_no": r.get("rcept_no"),
        }
        if len(latest) < 5:
            latest.append(item)
        if any(k.replace(" ", "") in title.replace(" ", "") for k in POSITIVE_KEYWORDS):
            positive.append(item)
        if any(k.replace(" ", "") in title.replace(" ", "") for k in RISK_KEYWORDS):
            risk.append(item)

    disc_score = min(5.0, len(positive) * 2.0)
    risk_penalty = min(10.0, len(risk) * 5.0)
    return {
        "positive": positive[:5],
        "risk": risk[:5],
        "latest": latest,
        "disclosure_score": disc_score,
        "risk_penalty": risk_penalty,
    }


def final_score(base: float, fin: float, disc: float, risk_penalty: float) -> float:
    # 키움 기반 점수 80% + 실적 15 + 공시 5 - 위험공시 최대 10
    score = float(base or 0) * 0.80 + fin + disc - risk_penalty
    return round(max(0.0, min(100.0, score)), 1)


def main():
    api_key = os.getenv("DART_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DART_API_KEY가 없습니다. 환경변수에 OpenDART 인증키를 먼저 넣어주세요.")
    if not DATA_PATH.exists():
        raise SystemExit(f"{DATA_PATH} 파일이 없습니다. 키움 수집기를 먼저 실행해주세요.")

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    stocks = payload.get("stocks") or []
    print(f"[DART] 기업코드 내려받는 중 / 대상 {len(stocks)}종목")
    corp_map = load_corp_map(api_key)
    print(f"[DART] 상장사 코드 {len(corp_map):,}개 매핑 완료")

    errors = []
    for idx, s in enumerate(stocks, 1):
        code = str(s.get("code", ""))
        name = s.get("name", "")
        corp_code = corp_map.get(code)
        print(f"[{idx}/{len(stocks)}] {name} {code}")
        if not corp_code:
            s["dart_status"] = "고유번호 없음"
            continue
        try:
            fin = financials(api_key, corp_code)
            time.sleep(REQUEST_DELAY)
            disc = disclosures(api_key, corp_code)
            time.sleep(REQUEST_DELAY)

            s["corp_code"] = corp_code
            s.update(fin)
            s["dart_disclosures"] = disc
            s["op_yoy"] = fin.get("op_yoy")
            s["score_final"] = final_score(
                s.get("score_base", 0),
                fin.get("financial_score", 0),
                disc.get("disclosure_score", 0),
                disc.get("risk_penalty", 0),
            )
            if disc.get("risk"):
                s["disclosure"] = "주의공시"
            elif disc.get("positive"):
                s["disclosure"] = "긍정후보공시"
            else:
                s["disclosure"] = "특이공시 없음"
            s["stage"] = "집중관찰" if s["score_final"] >= 80 else "관찰" if s["score_final"] >= 70 else "대기"
            s["dart_status"] = "완료"
        except Exception as e:
            s["dart_status"] = f"오류: {e}"
            errors.append({"code": code, "name": name, "error": str(e)})

    stocks.sort(key=lambda x: x.get("score_final", x.get("score_base", 0)), reverse=True)
    payload["stocks"] = stocks
    payload["version"] = "stock-miner-v4-dart"
    payload["note"] = "키움 3개 후보경로 + 5일수급/거래량/이평선 + OpenDART 실적/최근90일 공시 휴리스틱을 결합. 공시 분류는 제목 키워드 기반 후보 신호이며 투자판단이 아님."
    payload["dart"] = {
        "api_key_detected": True,
        "status": "연결 완료",
        "lookback_days": LOOKBACK_DAYS,
        "errors": errors,
    }
    payload["generated_at_dart"] = datetime.now().isoformat(timespec="seconds")
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[DART 완료] {DATA_PATH.resolve()}")
    print(f"성공 {len(stocks) - len(errors)}개 / 오류 {len(errors)}개")
    print("상위 10개:")
    for r in stocks[:10]:
        print(f"{r.get('score_final', r.get('score_base', 0)):>5} {r.get('name',''):<16} 실적YoY {r.get('op_yoy')} 공시 {r.get('disclosure')}")


if __name__ == "__main__":
    main()
