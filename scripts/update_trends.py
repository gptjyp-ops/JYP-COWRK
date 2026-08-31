#!/usr/bin/env python3
import json, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

URL = "https://trends.google.com/trending/rss?geo=KR"
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

def public_ranking(name):
    # 공개 순위 제공 페이지의 JSON 결과를 한 시간마다 보관합니다.
    payload=json.loads(request(f"https://adsensefarm.kr/realtime/{name}.php"))
    if payload.get("result") != "success":
        raise RuntimeError(f"{name} ranking unavailable")
    return {
        "updated": payload.get("nowtime", ""),
        "items": [{"k":str(k).strip(), "m":"실시간 인기 검색어"}
                  for k in payload.get("data", [])[:10] if str(k).strip()]
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
    ("daum", lambda: public_ranking("daum")),
    ("creator", lambda: public_ranking("naver")),
):
    try:
        sources[key]=loader()
    except Exception as exc:
        if previous.get("sources", {}).get(key):
            sources[key]=previous["sources"][key]
            sources[key]["stale"]=True
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
