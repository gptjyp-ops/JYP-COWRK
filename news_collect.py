from __future__ import annotations

import json
import argparse
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from stock_miner_watchlist import include_watchlist, load_watchlist
from momentum_themes import THEMES, SPORTS, build_themes, company_match, recent

PARTS = [Path(f"data/stock-miner-v4-part{i}.json") for i in (1, 2, 3)]
OUT = Path("data/news-momentum.json")
STATUS = Path("data/news-momentum-status.json")
DAYS = 7
MAX_ITEMS = 100
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
    "하향", "목표가 하향", "급락", "약세", "하락", "소송", "제재", "리콜", "중단", "해지", "철회", "실패",
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
    return include_watchlist(rows)


def rss_search(name: str, domain: str, *, theme_search=False, code="") -> list[dict]:
    query = f'({name}) site:{domain} when:{DAYS}d' if theme_search else f'"{name}" site:{domain} when:{DAYS}d'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query,
        "hl": "ko",
        "gl": "KR",
        "ceid": "KR:ko",
    })
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 StockMiner/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                root = ET.fromstring(r.read())
            break
        except (urllib.error.URLError, TimeoutError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

    out = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source_node = item.find("source")
        source = (source_node.text or "").strip() if source_node is not None else ""
        if SPORTS.search(title) or (not theme_search and not company_match(title, name, code)):
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
            "published": dt.astimezone(timezone.utc).isoformat() if dt else pub,
            "source": source,
        })
    return sorted(out, key=lambda x: x.get("published", ""), reverse=True)[:MAX_ITEMS]

def article_key(item):
    title=re.sub(r"\s+-\s+[^-]+$", "", item.get("title", ""))
    return re.sub(r"[\W_]+", "", title).casefold()

def track_articles(items, previous, observed_at):
    old={article_key(x):x for x in previous if article_key(x)}
    result, seen=[], set()
    for item in sorted(items, key=lambda x:x.get("published", ""), reverse=True):
        key=article_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        first_seen=old[key].get("first_seen_at") if key in old else observed_at
        result.append(dict(item, first_seen_at=first_seen))
    return result[:20]


def score_news(items: list[dict], now=None) -> tuple[int, str, list[str]]:
    score = 0.0
    reasons = []
    now = now or datetime.now(timezone.utc)
    items = [x for x in items if recent(x, now) and not SPORTS.search(x.get("title", ""))]
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
        if any(k in title for k in ("해지", "철회", "실패")):
            pos = []
        if pos:
            score += (2.0 if any(k in title for k in STRONG) else 1.0) * age_weight
            reasons.extend(pos[:1])
        if neg:
            score -= 1.5 * age_weight
            reasons.extend([f"주의:{neg[0]}"])

    # 기사 수 자체는 관심도 신호로 아주 작게만 반영
    score += min(2.0, len(items) * 0.35)
    score = int(round(max(0.0, min(10.0, score))))
    label = "강함" if score >= 4 else "형성중" if score >= 2 else "약함"
    return score, label, list(dict.fromkeys(reasons))[:5]


def collect_payload(watch_only=False):
    stocks = load_watchlist() if watch_only else load_stocks()
    previous={}
    if OUT.exists():
        try:
            previous=json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    if not stocks:
        raise RuntimeError("시세 종목 목록이 비어 있어 뉴스 게시를 중단합니다.")
    result = {}
    successful_queries = 0
    attempted_queries = 0
    public_feeds={}
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
            attempted_queries += 1
            try:
                if watch_only:
                    # 관심종목명·코드는 외부로 보내지 않고 공개 기업뉴스를 내부 대조합니다.
                    if domain not in public_feeds:
                        public_feeds[domain]=rss_search("증시 OR 기업 OR 실적 OR 수주", domain, theme_search=True)
                    found=[x for x in public_feeds[domain] if company_match(x.get("title", ""), name, code)]
                else:
                    found = rss_search(name, domain, code=code)
                successful_queries += 1
                found = [x for x in found if recent(x, datetime.now(timezone.utc))]
                for x in found:
                    x["source_group"] = source_name
                items.extend(found)
            except Exception as e:
                errors.append(f"{source_name}: {e}")
            time.sleep(REQUEST_DELAY)

        checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds")
        old=previous.get("stocks", {}).get(code, {})
        if watch_only:
            # 공개 피드의 상위 목록에서 벗어난 기사도 7일 동안 유지합니다.
            items += [x for x in old.get("news", []) if recent(x, datetime.now(timezone.utc))]
        dedup=track_articles(items, old.get("news", []), checked_at)
        if errors and not dedup and old.get("news"):
            result[code]=dict(old, errors=errors, news_status="error", checked_at=checked_at)
            continue

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
            "checked_at": checked_at,
            "news_status": "partial" if errors and dedup else "error" if errors else "ok" if dedup else "no_articles",
        }
        # Stop a widespread outage without repeatedly hammering the same RSS service.
        if attempted_queries >= 6 and successful_queries == 0:
            raise RuntimeError("뉴스 조회가 연속 실패했습니다. 기존 게시 자료를 보존합니다. " + "; ".join(errors))

    independent, theme_errors = {}, {}
    for key, label, _, query, _ in ([] if watch_only else THEMES):
        independent[key], theme_errors[key] = [], []
        print(f"[관심 모멘텀] {label}")
        for source_name, domain in SOURCES:
            attempted_queries += 1
            try:
                found = rss_search(query, domain, theme_search=True)
                successful_queries += 1
                independent[key].extend(dict(x, source_group=source_name) for x in found)
            except Exception as e:
                theme_errors[key].append(f"{source_name}: {e}")
            time.sleep(REQUEST_DELAY)

    if successful_queries == 0:
        raise RuntimeError("뉴스 조회가 모두 실패했습니다. 기존 게시 자료를 보존합니다.")

    if watch_only:
        return dict(previous, stocks={**previous.get("stocks", {}), **result},
                    watch_checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    collection_status="partial" if successful_queries < attempted_queries else "ok",
                    successful_queries=successful_queries, attempted_queries=attempted_queries)
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "version": "stock-miner-news-v1",
        "lookback_days": DAYS,
        "sources": [x[0] for x in SOURCES],
        "stocks": result,
        "input_generated_at": json.loads(Path("data/stock-miner-v4-meta.json").read_text(encoding="utf-8")).get("generated_at") if Path("data/stock-miner-v4-meta.json").exists() else None,
        "matching_revision": "company-boundary-v2",
        "collection_status": "partial" if successful_queries < attempted_queries else "ok",
        "successful_queries": successful_queries,
        "attempted_queries": attempted_queries,
        "themes": build_themes(stocks, result, independent, theme_errors),
        "theme_method": "최근 7일 기사·공시 제목 기반. 기업 업종 및 직접 수혜 확정 아님.",
    }
    return payload


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main(watch_only=False):
    attempted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        payload = collect_payload(watch_only=watch_only)
        write_json(OUT, payload)
    except Exception as error:
        write_json(STATUS, {
            "attempted_at": attempted_at,
            "status": "error",
            "message": str(error),
            "preserved_previous_data": OUT.exists(),
        })
        raise
    write_json(STATUS, {
        "attempted_at": attempted_at,
        "status": payload["collection_status"],
        "last_success_at": payload.get("watch_checked_at") if watch_only else payload["generated_at"],
        "successful_queries": payload["successful_queries"],
        "attempted_queries": payload["attempted_queries"],
        "preserved_previous_data": False,
    })
    print(f"완료: {OUT} / {len(payload['stocks'])}종목 / 조회 {payload['successful_queries']}/{payload['attempted_queries']} 성공")


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--watch-only", action="store_true")
    main(watch_only=parser.parse_args().watch_only)
