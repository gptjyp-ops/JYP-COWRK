"""Transparent observation priority; this is not a predicted return."""
from datetime import datetime, timezone, timedelta
import math
import re

KST = timezone(timedelta(hours=9))
EVENT = re.compile(r'수주|공급계약|계약\s*체결|양산|FDA|승인|허가|증설|투자유치|흑자전환', re.I)
NEGATIVE = re.compile(r'해지|철회|취소|실패|중단|소송|제재|리콜|유상증자|전환사채|감자')

def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else 0
    except (ValueError, TypeError):
        return 0

def timestamp(value):
    if not value:
        return None
    try:
        if re.fullmatch(r'\d{8}', str(value)):
            return datetime.strptime(value, '%Y%m%d').replace(tzinfo=KST)
        stamp = datetime.fromisoformat(value)
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=KST)
    except (ValueError, TypeError):
        return None

def priority(stock, news=None, now=None):
    now = now or datetime.now(timezone.utc)
    news = news or {}
    articles = news.get('news', []) if news.get('news_status') not in ('error', 'not_collected') else []
    filings = stock.get('dart_disclosures', {})
    evidence = articles + filings.get('positive', []) + filings.get('risk', [])
    seen, event_points, negative, hits = set(), 0, False, []
    for item in evidence:
        title = str(item.get('title', ''))
        key = re.sub(r'\[기재정정\]|\s+', '', title)
        stamp = timestamp(item.get('published') or item.get('date'))
        if not stamp or not title or key in seen:
            continue
        hours = (now - stamp).total_seconds() / 3600
        if not 0 <= hours <= 168:
            continue
        seen.add(key)
        if NEGATIVE.search(title):
            negative = True
        elif EVENT.search(title):
            event_points += 20 if hours <= 24 else 14 if hours <= 72 else 8
            hits.append(title)
    event_points = min(40, event_points)
    flow = (10 if number(stock.get('foreign5')) > 0 else 0) + (10 if number(stock.get('inst5')) > 0 else 0)
    volume = number(stock.get('vol_ratio'))
    volume_points = 20 if volume >= 2 else 15 if volume >= 1.5 else 8 if volume >= 1.2 else 0
    dist = number(stock.get('dist20'))
    change = number(stock.get('change'))
    position = 10 if -5 <= dist <= 8 and 0 <= change < 8 else 5 if abs(dist) <= 10 else 0
    financial = max(0, min(5, number(stock.get('financial_score')) / 3))
    risk = min(10, number(filings.get('risk_penalty')))
    penalty = (15 if negative else 0) + risk + (10 if change >= 8 or dist > 10 else 0)
    score = round(max(0, min(100, event_points + flow + volume_points + position + financial - penalty)), 1)
    reasons = []
    if hits: reasons.append('최근 7일 새 재료 후보')
    if flow == 20: reasons.append('외국인·기관 동반 순매수')
    elif flow: reasons.append('5일 순매수 확인')
    if volume_points: reasons.append('거래량 반응')
    if penalty: reasons.append('급등·주의 재료 감점')
    if not hits: reasons.append('새 재료 근거 미확인')
    return {'score': score, 'event_points': event_points, 'event_titles': hits[:3], 'reasons': reasons, 'penalty': penalty, 'revision': 'event-priority-1'}
