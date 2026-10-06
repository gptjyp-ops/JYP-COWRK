"""Prospective fixed-watch versus automatic cohort; no historical backfill."""
import copy
import json
from datetime import datetime
from pathlib import Path
from stock_miner_momentum import priority, timestamp, KST

PATH = Path(__file__).resolve().parent / 'data' / 'stock-miner-observations.json'

def include_pending(rows):
    result = [dict(row) for row in rows]
    codes = {str(row['code']) for row in result}
    if not PATH.exists():
        return result
    history = json.loads(PATH.read_text(encoding='utf-8'))
    for record in history.get('records', []):
        if record.get('baseline_price') and record.get('returns', {}).get('5') is None and record['code'] not in codes:
            result.append({'code': record['code'], 'name': record['name'], 'sources': [], 'comparison_only': True})
            codes.add(record['code'])
    return result

def update(history, stocks, audit, news, generated_at, watched):
    history = copy.deepcopy(history)
    now = timestamp(generated_at)
    if now is None:
        raise ValueError('관찰 기록 수집 시각 오류')
    start = timestamp(history['tracking_started_at'])
    rows = {str(s['code']): s for s in stocks}
    history['updated_at'] = generated_at
    # The first actual PC collection after enrollment fixes both cohorts together.
    fresh = all(timestamp(s.get('collected_at') or generated_at) and timestamp(s.get('collected_at') or generated_at) >= start for s in stocks)
    if not history.get('cohort_at') and stocks and now >= start and fresh:
        history['cohort_at'] = generated_at
        fixed = {str(s['code']): s for s in watched}
        ranked = sorted((s for s in stocks if s['code'] not in fixed and not s.get('comparison_only')), key=lambda s: (-priority(s, news.get('stocks', {}).get(s['code']), now)['score'], s['code']))[:10]
        entries = [('관심', item) for item in watched] + [('자동', item) for item in ranked]
        history['records'] = []
        for group, item in entries:
            s = rows.get(item['code'])
            sample = audit.get(item['code'], {}).get('chart', {}).get('rows', [])
            baseline = s.get('price') if s else None
            history['records'].append({'group': group, 'code': item['code'], 'name': item['name'], 'baseline_price': baseline, 'baseline_date': s.get('quote_date') if s else None, 'baseline_collected_at': s.get('collected_at', generated_at) if s else None, 'previous_close': copy.deepcopy(sample[1]) if len(sample) > 1 else None, 'priority_at_start': priority(s, news.get('stocks', {}).get(item['code']), now)['score'] if s else None, 'returns': {'1': None, '3': None, '5': None}, 'return_dates': {}, 'status': 'tracking' if baseline else 'missing_baseline'})
    today = now.astimezone(KST).strftime('%Y%m%d')
    for record in history.get('records', []):
        if not record.get('baseline_price'):
            continue
        sample = audit.get(record['code'], {}).get('chart', {}).get('rows', [])
        previous = record.get('previous_close')
        matching = next((r for r in sample if previous and r['date'] == previous['date']), None)
        if matching and abs(matching['price'] - previous['price']) > 0.01:
            record['status'] = 'adjustment_review'
            record['returns'] = {'1': None, '3': None, '5': None}
            continue
        if record.get('status') == 'adjustment_review':
            continue
        # Ignore today's unfinished daily bar at every intraday collection.
        future = sorted((r for r in sample if record['baseline_date'] < r['date'] < today), key=lambda r: r['date'])
        for day in (1, 3, 5):
            key = str(day)
            if record['returns'].get(key) is None and len(future) >= day:
                bar = future[day - 1]
                record['returns'][key] = round((bar['price'] / record['baseline_price'] - 1) * 100, 2)
                record['return_dates'][key] = bar['date']
        record['status'] = 'complete' if record['returns']['5'] is not None else 'tracking'
    return history
