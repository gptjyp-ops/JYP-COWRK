#!/usr/bin/env python3
import json, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

URL = "https://trends.google.com/trending/rss?geo=KR"
req = urllib.request.Request(URL, headers={"User-Agent":"Mozilla/5.0 JYP-COWRK/1.0"})
with urllib.request.urlopen(req, timeout=30) as res:
    root = ET.fromstring(res.read())
items=[]
for node in root.findall("./channel/item")[:20]:
    title=(node.findtext("title") or "").strip()
    traffic=""
    for child in node:
        if child.tag.endswith("approx_traffic"):
            traffic=(child.text or "").strip()
    if title:
        items.append({"k":title,"m":f"검색량 {traffic}" if traffic else "Google Trends"})
now=datetime.now(timezone.utc)
kst=now.astimezone(timezone(timedelta(hours=9)))
data={"source":"Google Trends KR RSS","updated_at":now.isoformat(),"updated_kst":kst.strftime("%Y년 %m월 %d일 %H:%M"),"items":items}
out=Path(__file__).resolve().parents[1]/"data"/"trends.json"
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(f"updated {len(items)} keywords")
