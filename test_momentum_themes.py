import unittest
from datetime import datetime, timezone
from momentum_themes import topic_ids, build_themes, annotate

class ThemeTests(unittest.TestCase):
    def test_thirteen_topics_and_boundaries(self):
        from momentum_themes import THEMES
        self.assertEqual(len(THEMES),13)
        self.assertEqual(topic_ids('자금 조달 계약 체결'),[])
        self.assertNotIn('ai',topic_ids('CHAIR 기업 실적'))
        self.assertIn('ai',topic_ids('AI 데이터센터 공급계약'))
        self.assertEqual(topic_ids('국제금 가격 급등'),['gold'])
    def test_cross_theme_and_negative_event(self):
        item=annotate({'title':'AI 데이터센터 전선 공급계약 해지'})
        self.assertEqual(set(item['theme_ids']),{'ai','cable'})
        self.assertIn('해지',item['risk_keywords'])
        self.assertIn('계약·수주',item['event_types'])
    def test_sports_excluded(self):
        self.assertEqual(topic_ids('기아 프로야구 AI 홈런 분석'),[])
    def test_independent_news_named_candidates_freshness(self):
        now=datetime(2026,9,30,3,tzinfo=timezone.utc)
        stocks=[{'code':'01','name':'테스트전선'}]
        items=[{'title':'테스트전선 AI 공급계약','published':'2026-09-29T12:00:00+09:00','link':'https://example.com'}, {'title':'테스트전선 전선 공급계약','published':'2020-01-01T00:00:00+00:00'}]
        topics=build_themes(stocks,{}, {'ai':items},now=now)
        ai=next(t for t in topics if t['id']=='ai')
        self.assertEqual(ai['candidates'][0]['code'],'01')
        self.assertEqual(len(ai['articles']),1)
        self.assertTrue(ai['independent_search'])
        self.assertEqual(next(t for t in topics if t['id']=='cable')['candidates'],[])
    def test_news_and_disclosure_candidates(self):
        now=datetime(2026,9,30,3,tzinfo=timezone.utc)
        stocks=[{'code':'01','name':'바이오회사','dart_disclosures':{'latest':[{'title':'신약 임상 승인','date':'20260929','rcept_no':'123'}]}}]
        themes=build_themes(stocks,{},now=now)
        bio=next(t for t in themes if t['id']=='bio')
        self.assertEqual(bio['candidates'][0]['evidence'][0]['source'],'DART')
        self.assertEqual(bio['candidates'][0]['evidence'][0]['link'],'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=123')

if __name__=='__main__':unittest.main()
