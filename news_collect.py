from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

PARTS = [Path(f"data/stock-miner-v4-part{i}.json") for i in (1, 2, 3)]
OUT = Path("data/news-momentum.json")
DAYS = 7
MAX_ITEMS = 6
REQUEST_DELAY = 0.25

SOURCES = [
    ("머니투데이", "mt.co.kr"),
    ("연합뉴스", "yna.co.kr"),
]

POSITIVE = (
    "수주", "공급계약", "계약 체결", "승인", "허가", "FDA", "증설", "시설투자",
    "신사업", "신규사업", "투자유치", "흑자전환", "실적 개선", "최대 실적", "상향",
    "목표가 상향", "수혜", "반등", "급등", "강세", "회복", "출시", "양산", "특허",
)
NEGATIVE = (
    "유상증자", "전환사채", "CB", "감자", "최대주주 변경", "적자", "실적 부진",
    "하향", "목표가 하향", "급락", "약세", "하락", "소송", "제재", "리콜", "중단",
)
STRONG = ("수주", "공급계약", "FDA", "흑자전환", "증설", "투자유치", "양산", "특허")


def load_stocks() -> list[dict]:
    rows = []
    for p in PARTS:
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            rows.extend(data)
        elif isinstance(data, dict):
            rows.extend(data.get("stocks") or [])
    return rows


def rss_search(name: str, domain: str) -> list[dict]:
    query = f'"{name}" site:{domain} when:{DAYS}d'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query,
        "hl": "ko",
        "gl": "KR",
        "ceid": "KR:ko",
    })
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 StockMiner/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())

    out = []
    for item in root.findall("./channel/item")[:MAX_ITEMS]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source_node = item.find("source")
        source = (source_node.text or "").strip() if source_node is not None else ""
        if name not in title:
            continue
        dt = None
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
        out.append({
            "title": title,
            "link": link,
            "published": dt.isoformat() if dt else pub,
            "source": source,
        })
    return out


def score_news(items: list[dict]) -> tuple[int, str, list[str]]:
    score = 0.0
    reasons = []
    now = datetime.now(timezone.utc)
    for item in items:
        title = item.get("title", "")
        age_weight = 1.0
        try:
            dt = datetime.fromisoformat(item.get("published", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            hours = max(0.0, (now - dt.astimezone(timezone.utc)).total_seconds() / 3600)
            age_weight = 1.0 if hours <= 24 else 0.7 if hours <= 72 else 0.4
        except Exception:
            pass

        pos = [k for k in POSITIVE if k.lower() in title.lower()]
        neg = [k for k in NEGATIVE if k.lower() in title.lower()]
        if pos:
            score += (2.0 if any(k in title for k in STRONG) else 1.0) * age_weight
            reasons.extend(pos[:1])
        if neg:
            score -= 1.5 * age_weight
            reasons.extend([f"주의:{neg[0]}"])

    # 기사 수 자체는 관심도 신호로 아주 작게만 반영
    score += min(2.0, len(items) * 0.35)
    score = int(round(max(0.0, min(10.0, score))))
    label = "강함" if score >= 7 else "형성중" if score >= 4 else "약함"
    return score, label, list(dict.fromkeys(reasons))[:5]


def main():
    stocks = load_stocks()
    result = {}
    print(f"[뉴스] {len(stocks)}종목 / 머니투데이+연합뉴스 / 최근 {DAYS}일")

    for idx, s in enumerate(stocks, 1):
        code = str(s.get("code", ""))
        name = str(s.get("name", "")).strip()
        if not code or not name:
            continue
        print(f"[{idx}/{len(stocks)}] {name}")
        items = []
        errors = []
        for source_name, domain in SOURCES:
            try:
                found = rss_search(name, domain)
                for x in found:
                    x["source_group"] = source_name
                items.extend(found)
            except Exception as e:
                errors.append(f"{source_name}: {e}")
            time.sleep(REQUEST_DELAY)

        # 제목 중복 제거
        dedup = []
        seen = set()
        for x in sorted(items, key=lambda z: z.get("published", ""), reverse=True):
            key = x.get("title", "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            dedup.append(x)
        dedup = dedup[:8]

        score, label, reasons = score_news(dedup)
        result[code] = {
            "code": code,
            "name": name,
            "news_score": score,
            "news_label": label,
            "news_count": len(dedup),
            "news_reasons": reasons,
            "news": dedup,
            "errors": errors,
        }

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "version": "stock-miner-news-v1",
        "lookback_days": DAYS,
        "sources": [x[0] for x in SOURCES],
        "stocks": result,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료: {OUT} / {len(result)}종목")


if __name__ == "__main__":
    main()
