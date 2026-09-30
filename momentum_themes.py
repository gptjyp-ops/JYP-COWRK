"""Evidence-based topic matching; these tags are not company sector classifications."""
import re
from datetime import datetime, timezone

THEMES = [
    ('gold','금',['금값','금 가격','금가격','국제 금','국제금','금 선물','금선물','금광','귀금속','골드'], '금값 OR 국제금 OR 금광', '금 가격·달러·금리 변화'),
    ('cable','전선',['전선','전력망','송전','해저케이블','전력 케이블','전력케이블'], '전선 OR 전력망 OR 해저케이블', '공급계약·송전망 투자·구리 가격'),
    ('semiconductor','반도체',['반도체','HBM','메모리','파운드리','웨이퍼'], '반도체 OR HBM OR 파운드리', '메모리 가격·수주·증설·양산'),
    ('aerospace','우주항공',['우주','항공우주','위성','발사체','누리호'], '우주항공 OR 위성 OR 발사체', '발사·위성 계약·정부 예산'),
    ('oil','유가',['유가','원유','WTI','브렌트','OPEC'], '국제유가 OR 원유 OR OPEC', '원유 가격·감산·공급 차질'),
    ('ai','AI',['AI','인공지능','데이터센터','데이터 센터','GPU'], '인공지능 OR AI OR 데이터센터', '인프라 투자·서비스 계약·전력 수요'),
    ('defense','방산',['방산','방위산업','방위 산업','무기','미사일','전투기','국방','K9'], '방산 OR 무기 수출 OR 국방', '수출 계약·수주·국방 예산'),
    ('telecom','통신',['통신','5G','6G','통신망','광통신'], '통신 OR 6G OR 광통신', '망 투자·요금 정책·설비 계약'),
    ('battery','2차전지',['2차전지','이차전지','배터리','양극재','음극재','리튬','전고체'], '이차전지 OR 배터리 OR 리튬', '공급계약·원재료·전기차 수요'),
    ('shipping','해운',['해운','운임','컨테이너','선박','SCFI','BDI','해상운송'], '해운 OR 운임 OR SCFI', '운임·항로 차질·물동량'),
    ('robot','로봇',['로봇','로보틱스','휴머노이드','협동로봇'], '로봇 OR 휴머노이드 OR 로보틱스', '공급계약·양산·기업 투자'),
    ('beauty','화장품',['화장품','뷰티','코스메틱','스킨케어'], '화장품 OR 뷰티 OR 코스메틱', '수출·해외 유통·판매 실적'),
    ('bio','바이오',['바이오','신약','임상','FDA','기술수출','기술 수출','제약'], '바이오 OR 신약 OR 임상', '임상 결과·허가·기술이전 계약'),
]
SPORTS = re.compile(r'야구|프로야구|KBO|타율|홈런|선발투수|타석|승점|챔피언스리그|골키퍼')
EVENTS = [('계약·수주',['수주','공급계약','계약 체결','계약체결','기술이전','기술수출']),('투자·생산',['증설','양산','시설투자','투자유치']),('허가·임상',['FDA','승인','허가','임상']),('실적',['실적','흑자','적자','매출']),('가격·수요',['금값','유가','운임','수요','가격'])]
RISKS = ['유상증자','전환사채','적자','급락','하락','소송','제재','리콜','중단','실패','철회','해지']


def contains(title, word):
    if word.isascii():
        return bool(re.search(r'(?<![A-Za-z0-9])'+re.escape(word)+r'(?![A-Za-z0-9])',title,re.I))
    return word in title


def topic_ids(title):
    if SPORTS.search(title):
        return []
    return [key for key,_,words,_,_ in THEMES if any(contains(title,w) for w in words)]


def annotate(item):
    item = dict(item)
    title = str(item.get('title',''))
    item['theme_ids'] = topic_ids(title)
    item['event_types'] = [label for label,words in EVENTS if any(contains(title,w) for w in words)]
    item['risk_keywords'] = [w for w in RISKS if contains(title,w)]
    return item


def recent(item, now):
    try:
        stamp = datetime.fromisoformat(item['published']).astimezone(timezone.utc)
        return -300 <= (now-stamp).total_seconds() <= 7*86400
    except (ValueError, KeyError, TypeError):
        return False


def build_themes(stocks, news_map, independent=None, errors=None, now=None):
    now = now or datetime.now(timezone.utc)
    independent = independent or {}
    errors = errors or {}
    out = []
    for key,label,_,_,watch in THEMES:
        articles = []
        candidates = []
        for stock in stocks:
            code = str(stock.get('code',''))
            items = news_map.get(code,{}).get('news',[])
            evidence = [annotate(x) for x in items if key in topic_ids(x.get('title','')) and recent(x,now) and str(stock.get('name','')) in x.get('title','')]
            for x in evidence:
                articles.append(dict(x, mentioned_codes=[code]))
            disclosure = stock.get('dart_disclosures',{})
            for x in disclosure.get('latest',[]):
                if key in topic_ids(x.get('title','')):
                    try:
                        date = datetime.strptime(x['date'],'%Y%m%d').replace(tzinfo=timezone.utc)
                        if not 0 <= (now-date).total_seconds() <= 7*86400: continue
                    except (KeyError, ValueError): continue
                    evidence.append(dict(annotate(x), source='DART', published=x['date'], link='https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+str(x.get('rcept_no',''))))
            if evidence:
                candidates.append({'code':code,'name':stock.get('name'),'evidence':evidence[:4]})
        for item in independent.get(key,[]):
            if key not in topic_ids(item.get('title','')) or not recent(item,now): continue
            item = annotate(item)
            item['mentioned_codes'] = [str(s['code']) for s in stocks if len(str(s.get('name','')))>=2 and str(s['name']) in item['title']]
            articles.append(item)
            for code in item['mentioned_codes']:
                candidate = next((s for s in candidates if s['code']==code),None)
                if candidate: candidate['evidence'] = (candidate['evidence']+[item])[:4]
                else:
                    stock = next(s for s in stocks if str(s['code'])==code)
                    candidates.append({'code':code,'name':stock['name'],'evidence':[item]})
        dedup = {}
        for item in articles:
            title = item['title']
            if title in dedup:
                dedup[title]['mentioned_codes'] = sorted(set(dedup[title]['mentioned_codes']+item['mentioned_codes']))
            else: dedup[title] = dict(item)
        out.append({'id':key,'label':label,'watch':watch,'articles':sorted(dedup.values(),key=lambda x:x.get('published',''),reverse=True)[:12], 'candidates':candidates,'errors':errors.get(key,[]),'independent_search':key in independent})
    return out
