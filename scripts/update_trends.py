#!/usr/bin/env python3
import json, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

URL = "https://trends.google.com/trending/rss?geo=KR"
SHOPPING_BEST_URL = "https://snxbest.naver.com/home"
HEADERS = {"User-Agent":"Mozilla/5.0 JYP-COWRK/1.0"}

def request(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()

def google_trends():
    root = ET.fromstring(request(URL))
    items=[]
    for node in root.findall("./channel/item")[:20]:
        title=(node.findtext("title") or "").strip()
        traffic=""
        for child in node:
            if child.tag.endswith("approx_traffic"):
                traffic=(child.text or "").strip()
        if title:
            items.append({"k":title,"m":f"검색량 {traffic}" if traffic else "Google Trends"})
    return {"items":items}

def naver_shopping_best():
    raw=request(SHOPPING_BEST_URL).decode("utf-8", errors="replace")
    marker='\\"keywordChartRankData\\":'
    start=raw.find(marker)
    if start < 0:
        raise RuntimeError("Naver shopping ranking data not found")
    start += len(marker)
    depth=0
    end=-1
    for pos, char in enumerate(raw[start:], start):
        if char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
            if depth == 0:
                end=pos+1
                break
    if end < 0:
        raise RuntimeError("Naver shopping ranking list incomplete")
    ranks=json.loads(raw[start:end].replace('\\"','"'))
    items=[]
    status_label={"NEW":"신규", "UP":"상승", "DOWN":"하락", "STABLE":"유지"}
    for x in ranks[:10]:
        title=str(x.get("title", "")).strip()
        if not title:
            continue
        movement=status_label.get(x.get("status"), "인기")
        change=x.get("rankFluctuation")
        if change and x.get("status") in ("UP", "DOWN"):
            movement += f" {abs(int(change))}"
        category=str(x.get("subTitle", "쇼핑")).strip()
        query=urllib.parse.quote(title)
        items.append({
            "k":title,
            "m":f"{category} · {movement}",
            "url":f"https://shopping.naver.com/ns/search?query={query}",
            "tag":"buy",
        })
    sync=str(ranks[0].get("syncDate", "")) if ranks else ""
    return {"updated":sync, "items":items}

def valid_keyword(value):
    return isinstance(value, str) and value.strip().lower() not in ("", "none", "null", "undefined")

def daum_trends():
    # 공식 홈페이지에 포함된 실시간 트렌드 데이터를 직접 읽습니다.
    raw=request("https://www.daum.net/").decode("utf-8", errors="replace")
    marker=re.search(r"window\.tillerInitData\s*=\s*", raw)
    if not marker:
        raise RuntimeError("다음 공식 페이지의 트렌드 데이터를 찾지 못했습니다.")
    payload, _=json.JSONDecoder().raw_decode(raw[marker.end():])
    def find(node):
        if isinstance(node, dict):
            if node.get("uiType") == "REALTIME_TREND_TOP":
                return node.get("contents", {}).get("data", {})
            for value in node.values():
                found=find(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found=find(value)
                if found is not None:
                    return found
        return None
    data=find(payload) or {}
    items=[]
    for entry in data.get("keywords", []):
        title=entry.get("keyword")
        if not valid_keyword(title):
            continue
        rank=entry.get("displayRank")
        if not isinstance(rank, int) or rank < 1:
            continue
        title=title.strip()
        items.append({"k":title, "rank":rank, "m":"다음 공식 실시간 트렌드",
                      "url":"https://search.daum.net/search?w=tot&q="+urllib.parse.quote(title)})
    items.sort(key=lambda item: item["rank"])
    if not items:
        raise RuntimeError("다음 공식 실시간 트렌드가 비어 있습니다.")
    return {"updated":data.get("updatedAt", ""), "provider":"Daum official",
            "source_url":"https://www.daum.net/", "items":items[:10]}

def public_ranking(name):
    # 공개 순위 제공 페이지의 JSON 결과를 한 시간마다 보관합니다.
    payload=json.loads(request(f"https://adsensefarm.kr/realtime/{name}.php"))
    if payload.get("result") != "success":
        raise RuntimeError(f"{name} ranking unavailable")
    items=[{"k":k.strip(), "m":"실시간 인기 검색어"}
           for k in payload.get("data", []) if valid_keyword(k)][:10]
    if not items:
        raise RuntimeError(f"{name} ranking contains no valid keywords")
    return {
        "updated": payload.get("nowtime", ""),
        "items": items
    }

out=Path(__file__).resolve().parents[1]/"data"/"trends.json"
previous={}
if out.exists():
    try:
        previous=json.loads(out.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

sources={}
for key, loader in (
    ("google", google_trends),
    ("shopping", naver_shopping_best),
    ("daum", daum_trends),
    ("creator", lambda: public_ranking("naver")),
):
    try:
        sources[key]=loader()
    except Exception as exc:
        old=previous.get("sources", {}).get(key, {})
        valid_items=[item for item in old.get("items", []) if valid_keyword(item.get("k"))]
        if valid_items:
            sources[key]={**old, "items":valid_items, "stale":True, "error":str(exc)}
        else:
            sources[key]={"items":[], "error":str(exc)}
now=datetime.now(timezone.utc)
kst=now.astimezone(timezone(timedelta(hours=9)))
data={
    "source":"Google Trends KR RSS + public realtime rankings",
    "updated_at":now.isoformat(),
    "updated_kst":kst.strftime("%Y년 %m월 %d일 %H:%M"),
    "sources":sources,
    # 이전 페이지와의 호환용
    "items":sources.get("google", {}).get("items", [])
}
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("updated " + ", ".join(f"{k}={len(v.get('items', []))}" for k,v in sources.items()))
