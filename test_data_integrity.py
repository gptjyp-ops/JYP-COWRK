"""Offline regression tests: no broker credentials or network requests."""
import importlib.util
import sys
import types
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

broker = types.ModuleType('kiwoom')
broker.get_client = lambda: None
broker.KiwoomError = RuntimeError
# Stubs exist only within import; no installed client or credentials are touched.
with patch.dict(sys.modules, {'kiwoom':broker}):
    collector = module('stock_miner_collect')
try:
    import requests
except ImportError:
    requests = types.ModuleType('requests')
    requests.RequestException = RuntimeError
    requests.get = lambda *a,**k: None
    with patch.dict(sys.modules, {'requests':requests}):
        dart = module('dart_enrich')
else:
    dart = module('dart_enrich')
from momentum_themes import company_match, build_themes
import news_collect
import stock_miner_watchlist

class FixedWatchlistTests(unittest.TestCase):
    def setUp(self):
        loader = patch.object(stock_miner_watchlist, 'load_watchlist', return_value=[{'code': '347700', 'name': '스피어', 'fixed_watch': True}, {'code': '105740', 'name': '디케이락', 'fixed_watch': True}])
        loader.start()
        self.addCleanup(loader.stop)

    def test_registered_stocks_are_included_once_without_source_bonus(self):
        rows = [{'code': '347700', 'name': '스피어', 'sources': ['거래량상위']}]
        result = stock_miner_watchlist.include_watchlist(rows)
        self.assertEqual([r['code'] for r in result], ['347700', '105740'])
        self.assertTrue(all(r['fixed_watch'] for r in result))
        self.assertEqual(result[0]['sources'], ['거래량상위'])
        self.assertEqual(result[1]['sources'], [])
        self.assertNotIn('fixed_watch', rows[0])

    def test_empty_rankings_still_collect_fixed_stocks(self):
        with patch.object(collector, 'collect_foreign_streak'), patch.object(collector, 'collect_institution_top'), patch.object(collector, 'collect_volume_top'), patch.object(collector.time, 'sleep'):
            rows, _ = collector.collect_candidates()
        self.assertEqual({r['code'] for r in rows}, {'347700', '105740'})

    def test_news_tracks_fixed_stocks_without_market_parts(self):
        with patch.object(news_collect, 'PARTS', []):
            rows = news_collect.load_stocks()
        self.assertEqual({r['code'] for r in rows}, {'347700', '105740'})

class DataIntegrityTests(unittest.TestCase):
    def test_company_boundaries_and_ambiguous_acronyms(self):
        self.assertFalse(company_match('SSG 아빌라 완투승', 'SG', '255220'))
        self.assertFalse(company_match('제이엘케이 AI 뇌영상 DB 연구 발표', 'DB', '012030'))
        self.assertFalse(company_match('DB하이텍 실적 개선', 'DB', '012030'))
        self.assertTrue(company_match('DB(012030) 영업이익 증가', 'DB', '012030'))
        self.assertTrue(company_match('SG, 공급계약 체결', 'SG', '255220'))
        self.assertFalse(company_match('현대바이오랜드 수주', '현대바이오', '048410'))
        self.assertTrue(company_match('대한전선은 공급계약 체결', '대한전선', '001440'))
        self.assertFalse(company_match('현대모비스 감독 인터뷰', '현대모비스', '012330'))
    def test_empty_and_missing_investor_is_not_zero(self):
        with patch.object(collector, 'fetch', return_value=[]):
            with self.assertRaises(RuntimeError): collector.investor_5d('005930')
        today=datetime.now(collector.KST)
        rows=[{'dt':(today-timedelta(days=i)).strftime('%Y%m%d'),'frgnr_invsr':'0','orgn':'0','ind_invsr':'0'} for i in range(5)]
        with patch.object(collector,'fetch',return_value=rows):
            self.assertEqual(collector.investor_5d('005930'),(0,0,0))
        del rows[0]['orgn']
        with patch.object(collector,'fetch',return_value=rows):
            with self.assertRaises(RuntimeError): collector.investor_5d('005930')
    def test_chart_sort_alignment_and_missing_value(self):
        today=datetime.now(collector.KST)
        rows=[{'dt':(today-timedelta(days=i)).strftime('%Y%m%d'),'cur_prc':str(100-i),'trde_qty':str(210 if i==0 else 100)} for i in range(60)]
        with patch.object(collector,'fetch',return_value=list(reversed(rows))):
            price,change,volume,d20,d60=collector.chart_metrics('005930')
            self.assertEqual(price,100)
            self.assertAlmostEqual(volume,2.1)
            self.assertAlmostEqual(change,(100/99-1)*100)
            self.assertAlmostEqual(d20,(100/90.5-1)*100)
        del rows[2]['cur_prc']
        with patch.object(collector,'fetch',return_value=rows):
            with self.assertRaises(RuntimeError): collector.chart_metrics('005930')
    def test_financial_account_statement_and_priority(self):
        rows=[{'sj_div':'CF','account_nm':'영업이익','account_id':'custom'}, {'sj_div':'IS','account_nm':'영업이익','account_id':'custom'}, {'sj_div':'IS','account_nm':'영업이익(손실)','account_id':'standard'}]
        self.assertIs(dart.find_account(rows,('영업이익',),('standard',)), rows[2])
        self.assertIsNone(dart.find_account(rows[:1],('영업이익',)))
        self.assertEqual(dart.profit_state(-50,-100),'loss_narrowing')
        self.assertEqual(dart.profit_state(50,-100),'turnaround')
        self.assertEqual(dart.profit_state(50,25),'profitable_growth')
    def test_dart_error_is_not_empty_disclosure(self):
        with patch.object(dart,'get_json',return_value={'status':'020'}):
            with self.assertRaises(RuntimeError): dart.disclosures('test','00000000')
            with self.assertRaises(RuntimeError): dart.financials('test','00000000')
        with patch.object(dart,'get_json',return_value={'status':'013'}):
            self.assertEqual(dart.disclosures('test','00000000')['status'],'no_filings')
            self.assertEqual(dart.financials('test','00000000')['financial_status'],'unavailable')
    def test_disclosures_beyond_twenty_and_pagination(self):
        ordinary=[{'report_nm':'정기보고서','rcept_no':str(i)} for i in range(100)]
        pages=[{'status':'000','total_page':2,'list':ordinary}, {'status':'000','total_page':2,'list':[{'report_nm':'유상증자결정','rcept_no':'101'}]}]
        with patch.object(dart,'get_json',side_effect=pages),patch.object(dart.time,'sleep'):
            result=dart.disclosures('test','00000000')
            self.assertEqual(result['queried_count'],101)
            self.assertEqual(len(result['risk']),1)
    def test_duplicate_theme_evidence_and_cancellation_score(self):
        now=datetime.now(timezone.utc)
        item={'title':'대한전선 공급계약 체결','published':now.isoformat(),'link':'https://example.com'}
        stock={'code':'001440','name':'대한전선'}
        themes=build_themes([stock],{'001440':{'news':[item]}},{'cable':[item]},now=now)
        cable=next(t for t in themes if t['id']=='cable')
        self.assertEqual(len(cable['candidates'][0]['evidence']),1)
        bad=dict(item,title='대한전선 공급계약 해지')
        self.assertLess(news_collect.score_news([bad],now)[0],news_collect.score_news([item],now)[0])
    def test_http_errors_do_not_publish_key(self):
        with patch.object(dart.requests,'get',side_effect=dart.requests.RequestException('URL crtfc_key=secret')):
            with self.assertRaises(RuntimeError) as error: dart.get_json('https://example.com',{})
        self.assertNotIn('secret',str(error.exception))

if __name__=='__main__': unittest.main()
