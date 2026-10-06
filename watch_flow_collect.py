"""Public investor-flow supplement; does not need a brokerage login."""
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from stock_miner_watchlist import load_watchlist

OUT = Path('data/watch-investor-flow.json')


def quantity(value):
    text = str(value).replace(',', '').strip()
    if not re.fullmatch(r'[+-]?\d+', text):
        raise ValueError('순매매량 미확인')
    return int(text)


def parse_flow(payload, code):
    if payload.get('itemCode') != code:
        raise ValueError('응답 종목코드 불일치')
    days = {}
    today = datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d')
    for row in payload.get('dealTrendInfos') or []:
        day = str(row.get('bizdate', ''))
        if not re.fullmatch(r'\d{8}', day) or day > today:
            continue
        datetime.strptime(day, '%Y%m%d')
        values = {key: quantity(row.get(field)) for key, field in (
            ('foreign', 'foreignerPureBuyQuant'), ('institution', 'organPureBuyQuant'))}
        if day in days and days[day] != values:
            raise ValueError('같은 날짜 수급 값 충돌')
        days[day] = values
    selected = sorted(days, reverse=True)[:5]
    if len(selected) < 5:
        raise ValueError('공개 수급 고유 일자 5개 미만')
    return {'foreign5': sum(days[d]['foreign'] for d in selected),
            'inst5': sum(days[d]['institution'] for d in selected),
            'investor_dates': selected, 'flow_source': '네이버 증권',
            'flow_unit': 'shares', 'flow_status': 'ok'}


def collect(stock):
    code = stock['code']
    checked = datetime.now(timezone.utc).isoformat(timespec='seconds')
    try:
        req = urllib.request.Request(f'https://m.stock.naver.com/api/stock/{code}/integration',
            headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=25) as response:
            data = json.load(response)
        flow = parse_flow(data, code)
        return dict(stock, **flow, collected_at=checked, checked_at=checked)
    except Exception as error:
        return dict(stock, flow_status='error', error=str(error), checked_at=checked)


def main():
    previous = json.loads(OUT.read_text()) if OUT.exists() else {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(collect, load_watchlist()))
    stocks = {}
    for row in results:
        old = previous.get('stocks', {}).get(row['code'], {})
        if row['flow_status'] == 'error' and old.get('foreign5') is not None:
            row = dict(old, flow_status='error', error=row['error'], checked_at=row['checked_at'])
        stocks[row['code']] = row
    payload = {'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'source': '네이버 증권 공개 투자자별 매매동향', 'unit': 'shares',
               'stocks': stocks}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('공개 수급:', sum(r['flow_status'] == 'ok' for r in results), '/', len(results))
    for row in results:
        if row['flow_status'] == 'error':
            print(row['name'], row['error'])


if __name__ == '__main__':
    main()
