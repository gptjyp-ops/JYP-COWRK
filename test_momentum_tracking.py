import copy
import unittest
from datetime import datetime
from unittest.mock import patch
from stock_miner_momentum import priority, timestamp
from stock_miner_observations import update, include_pending
import stock_miner_observations as observations

NOW = timestamp('2026-10-06T14:25:00+09:00')

class PriorityTests(unittest.TestCase):
    def test_new_event_outweighs_financial_bonus(self):
        stock = {'foreign5': 1, 'inst5': 1, 'vol_ratio': 1.5, 'dist20': 2, 'change': 3}
        strong_fin = dict(stock, financial_score=15)
        news = {'news_status': 'ok', 'news': [{'title': '신규 공급계약 체결', 'published': '2026-10-06T10:00:00+09:00'}]}
        self.assertGreater(priority(stock, news, NOW)['score'], priority(strong_fin, {}, NOW)['score'])

    def test_future_old_and_duplicate_evidence_do_not_boost_score(self):
        item = {'title': '공급계약 체결', 'date': '20261006'}
        base = priority({}, {'news': [item]}, NOW)
        news = {'news': [item, item, {'title': '미래 수주', 'date': '20261007'}, {'title': '오래된 수주', 'date': '20260901'}]}
        self.assertEqual(priority({}, news, NOW)['score'], base['score'])

    def test_cancelled_contract_and_hot_price_are_penalized(self):
        result = priority({'change': 12, 'dist20': 15}, {'news': [{'title': '공급계약 체결 해지', 'date': '20261006'}]}, NOW)
        self.assertEqual(result['event_points'], 0)
        self.assertGreater(result['penalty'], 0)

class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.history = {'tracking_started_at': '2026-10-06T12:52:33+09:00', 'cohort_at': None, 'records': []}
        self.rows = [{'code': '347700', 'name': '스피어', 'price': 100, 'quote_date': '20261006', 'collected_at': '2026-10-06T14:20:00+09:00'}, {'code': '105740', 'name': '디케이락', 'price': 200, 'quote_date': '20261006', 'collected_at': '2026-10-06T14:20:00+09:00'}, {'code': '005930', 'name': '자동 후보', 'price': 100, 'quote_date': '20261006', 'collected_at': '2026-10-06T14:20:00+09:00'}]
        self.watched = [{'code': '347700', 'name': '스피어'}, {'code': '105740', 'name': '디케이락'}]
        self.audit = {r['code']: {'chart': {'rows': [{'date': '20261006', 'price': r['price']}, {'date': '20261005', 'price': r['price']}]}} for r in self.rows}

    def enroll(self):
        return update(self.history, self.rows, self.audit, {}, NOW.isoformat(), self.watched)

    def test_no_backfill_from_pre_enrollment_data(self):
        self.assertIsNone(update(self.history, self.rows, self.audit, {}, '2026-10-06T09:25:00+09:00', self.watched)['cohort_at'])
        old = copy.deepcopy(self.rows)
        for r in old: r['collected_at'] = '2026-10-06T09:20:00+09:00'
        self.assertIsNone(update(self.history, old, self.audit, {}, NOW.isoformat(), self.watched)['cohort_at'])

    def test_cohort_is_fixed_and_same_day_is_not_day_one(self):
        history = self.enroll()
        self.assertEqual([r['group'] for r in history['records']], ['관심', '관심', '자동'])
        changed = copy.deepcopy(self.rows)
        changed[0]['price'] = 999
        again = update(history, changed, self.audit, {}, '2026-10-06T16:35:00+09:00', self.watched)
        self.assertEqual(again['records'][0]['baseline_price'], 100)
        self.assertIsNone(again['records'][0]['returns']['1'])

    def test_future_completed_bars_fill_returns_and_today_is_excluded(self):
        history = self.enroll()
        dates = ['20261007', '20261008', '20261009', '20261012', '20261013', '20261014']
        self.audit['347700']['chart']['rows'] = [{'date': d, 'price': 100 + (i + 1) * 10} for i, d in enumerate(dates)] + [{'date': '20261005', 'price': 100}]
        result = update(history, [], self.audit, {}, '2026-10-14T09:25:00+09:00', self.watched)
        self.assertEqual(result['records'][0]['returns'], {'1': 10.0, '3': 30.0, '5': 50.0})
        self.assertEqual(result['records'][0]['return_dates']['5'], '20261013')

    def test_dropped_candidates_remain_in_collection_until_day_five(self):
        history = self.enroll()
        with patch.object(observations.PATH.__class__, 'exists', return_value=True), patch.object(observations.PATH.__class__, 'read_text', return_value=__import__('json').dumps(history)):
            rows = include_pending([])
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r['comparison_only'] for r in rows))

    def test_adjusted_price_revision_does_not_create_false_return(self):
        history = self.enroll()
        self.audit['347700']['chart']['rows'][1]['price'] = 50
        result = update(history, [], self.audit, {}, '2026-10-08T09:25:00+09:00', self.watched)
        self.assertEqual(result['records'][0]['status'], 'adjustment_review')
        self.assertTrue(all(value is None for value in result['records'][0]['returns'].values()))

if __name__ == '__main__':
    unittest.main()
