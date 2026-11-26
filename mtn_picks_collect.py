"""Collect MTN '여의도 투자본부' stock picks and keep a cumulative source-tagged list."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("data/mtn-picks.json")
KST = timezone(timedelta(hours=9))
PROGRAMS = [
    ("1부", "https://www.mtn.co.kr/program/588/replay"),
    ("2부", "https://www.mtn.co.kr/program/589/replay"),
]
MAX_EPISODES_PER_PART = 8

THEME_RULES = [
    ("robot", re.compile(r"로봇|휴머노이드|감속기|액추에이터|스마트팩토리|물류로봇|피지컬\s*AI", re.I)),
    ("semiconductor", re.compile(r"반도체|HBM|D램|낸드|웨이퍼|파운드리|CXL|PCB", re.I)),
    ("bio", re.compile(r"바이오|제약|치료제|임상|의료|수술|황반변성", re.I)),
    ("retail", re.compile(r"화장품|ODM|뷰티|미용|블랙프라이데이", re.I)),
    ("telecom", re.compile(r"통신|5G|6G|RF|안테나|위성|우주|저궤도", re.I)),
    ("defense", re.compile(r"방산|국방|전차|미사일|함정|조선", re.I)),
    ("battery", re.compile(r"2차전지|이차전지|배터리|ESS|CNT|도전재", re.I)),
    ("cable", re.compile(r"전선|변압기|전력기기|케이블", re.I)),
    ("finance", re.compile(r"증권|투자|벤처|지주|금융", re.I)),
    ("ai", re.compile(r"인공지능|\bAI\b|소프트웨어|클라우드|보안", re.I)),
]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data):
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            text = " ".join(" ".join(self._parts).split())
            if text:
                self.links.append((self._href, text))
            self._href = None
            self._parts = []


def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 StockMiner/1.0",
            "Accept-Language": "ko-KR,ko;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def absolute_url(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)


def extract_stock_names(part: str, title: str) -> list[str]:
    clean = re.sub(r"\s+", " ", title).strip()
    if "여의도 투자본부" not in clean:
        return []
    if part == "1부":
        match = re.search(r"[\'‘“\"]([^\'’”\"]+?)[\'’”\"]\s*명예의 전당", clean)
        if not match:
            return []
        chunk = match.group(1)
        return [x.strip() for x in re.split(r"\s*,\s*", chunk) if x.strip()]
    after = re.sub(r"^.*?\]\s*", "", clean)
    after = re.sub(r",?\s*공략법은\?.*$", "", after)
    names = [x.strip(" '‘’“”\"") for x in re.split(r"\s+vs\s+", after, flags=re.I)]
    return [x for x in names if x]


def published_date(page_html: str) -> str | None:
    for pattern in (
        r'article:published_time[^>]+content=["\'](20\d{2}-\d{2}-\d{2})',
        r'(20\d{2}-\d{2}-\d{2})',
        r'(20\d{2})[./년\s-]+(\d{1,2})[./월\s-]+(\d{1,2})',
    ):
        match = re.search(pattern, page_html, re.I)
        if not match:
            continue
        if len(match.groups()) == 1:
            return match.group(1)
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return None


def page_plain_text(page_html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", page_html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def infer_theme(text: str) -> str:
    for theme, pattern in THEME_RULES:
        if pattern.search(text):
            return theme
    return "other"


def resolve_stock(name: str) -> dict | None:
    query = urllib.parse.urlencode(
        {
            "query": name,
            "target": "stock,index,marketindicator,coin,ipo",
        }
    )
    url = "https://m.stock.naver.com/front-api/search/autoComplete?" + query
    data = json.loads(fetch_text(url))
    items = ((data.get("result") or {}).get("items") or data.get("items") or [])
    if items and isinstance(items[0], list):
        flattened = []
        for group in items:
            if isinstance(group, list):
                flattened.extend(group)
        items = flattened
    exact = []
    fallback = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().upper()
        item_name = str(item.get("name") or "").strip()
        market = str(item.get("typeName") or item.get("typeCode") or "")
        if not re.fullmatch(r"[0-9A-Z]{6}", code):
            continue
        row = {"code": code, "name": item_name or name, "market": market}
        if item_name == name:
            exact.append(row)
        else:
            fallback.append(row)
    return exact[0] if exact else (fallback[0] if fallback else None)


def load_previous() -> dict:
    if not OUT.exists():
        return {"version": 1, "source": "MTN 여의도 투자본부", "stocks": []}
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "source": "MTN 여의도 투자본부", "stocks": []}


def collect_episodes() -> list[dict]:
    episodes = []
    seen_urls = set()
    for part, page_url in PROGRAMS:
        parser = LinkParser()
        parser.feed(fetch_text(page_url))
        picked = 0
        for href, title in parser.links:
            if picked >= MAX_EPISODES_PER_PART:
                break
            if f"여의도 투자본부 {part}" not in title:
                continue
            names = extract_stock_names(part, title)
            if not names:
                continue
            url = absolute_url(page_url, href)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                detail_html = fetch_text(url)
                date = published_date(detail_html)
                detail_text = page_plain_text(detail_html)
            except Exception:
                date = None
                detail_text = title
            episodes.append(
                {
                    "part": part,
                    "title": title,
                    "url": url,
                    "date": date,
                    "names": names,
                    "context": detail_text[:12000],
                }
            )
            picked += 1
    return episodes


def main():
    previous = load_previous()
    by_code = {str(x.get("code")): dict(x) for x in previous.get("stocks", []) if x.get("code")}
    by_name = {str(x.get("name")): str(x.get("code")) for x in by_code.values() if x.get("name")}
    today = datetime.now(KST).date().isoformat()
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    errors = []

    episodes = collect_episodes()
    for episode in episodes:
        episode_date = episode.get("date") or today
        episode_key = f"{episode['part']}|{episode['url']}"
        theme = infer_theme(episode.get("context") or episode["title"])
        for name in episode["names"]:
            resolved = None
            existing_code = by_name.get(name)
            if existing_code:
                resolved = {"code": existing_code, "name": name, "market": by_code[existing_code].get("market", "")}
            else:
                try:
                    resolved = resolve_stock(name)
                except Exception as error:
                    errors.append(f"{name}: 코드 조회 실패: {error}")
            if not resolved:
                errors.append(f"{name}: 종목코드 확인 불가")
                continue
            code = resolved["code"]
            row = by_code.get(code, {
                "code": code,
                "name": resolved.get("name") or name,
                "market": resolved.get("market") or "",
                "theme": theme,
                "first_seen": episode_date,
                "last_seen": episode_date,
                "mentions": 0,
                "episodes": [],
            })
            row["name"] = resolved.get("name") or row.get("name") or name
            if resolved.get("market"):
                row["market"] = resolved["market"]
            if row.get("theme") in (None, "", "other") and theme != "other":
                row["theme"] = theme
            eps = list(row.get("episodes") or [])
            if episode_key not in eps:
                eps.append(episode_key)
                row["mentions"] = int(row.get("mentions") or 0) + 1
            row["episodes"] = eps[-30:]
            row["first_seen"] = min(str(row.get("first_seen") or episode_date), episode_date)
            row["last_seen"] = max(str(row.get("last_seen") or episode_date), episode_date)
            if episode_date >= str(row.get("last_seen") or ""):
                row["latest_part"] = episode["part"]
                row["latest_episode"] = episode["title"]
                row["latest_url"] = episode["url"]
            by_code[code] = row
            by_name[row["name"]] = code

    stocks = sorted(by_code.values(), key=lambda x: (str(x.get("last_seen") or ""), int(x.get("mentions") or 0), x.get("name") or ""), reverse=True)
    payload = {
        "version": 1,
        "source": "MTN 여의도 투자본부",
        "source_urls": {"part1": PROGRAMS[0][1], "part2": PROGRAMS[1][1]},
        "generated_at": collected_at,
        "collection_status": "partial" if errors else "ok",
        "errors": errors,
        "stocks": stocks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"MTN PICK: {len(stocks)}종목 / 최근 에피소드 {len(episodes)}개 / 오류 {len(errors)}")


if __name__ == "__main__":
    main()
