import unittest
from watch_flow_collect import parse_flow, quantity

class PublicFlowTests(unittest.TestCase):
    def sample(self):
        return {'itemCode': '005930', 'dealTrendInfos': [
            {'bizdate': '202609'+str(day), 'foreignerPureBuyQuant': '+1,234', 'organPureBuyQuant': '-20'}
            for day in range(21, 26)]}

    def test_sum_signed_quantities_and_unique_days(self):
        data=self.sample()
        data['dealTrendInfos'].append(dict(data['dealTrendInfos'][0]))
        result=parse_flow(data,'005930')
        self.assertEqual(result['foreign5'],6170)
        self.assertEqual(result['inst5'],-100)
        self.assertEqual(len(result['investor_dates']),5)

    def test_missing_is_not_zero(self):
        with self.assertRaises(ValueError): quantity(None)
        with self.assertRaises(ValueError): quantity('-')
        data=self.sample();data['dealTrendInfos'][0]['organPureBuyQuant']=None
        with self.assertRaises(ValueError): parse_flow(data,'005930')

    def test_insufficient_history_or_wrong_stock_rejected(self):
        data=self.sample()
        with self.assertRaises(ValueError): parse_flow(data,'000660')
        data['dealTrendInfos'].pop()
        with self.assertRaises(ValueError): parse_flow(data,'005930')

if __name__ == '__main__': unittest.main()
