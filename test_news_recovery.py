"""Offline coverage for failed RSS runs, retries, and preserving published data."""
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock
import news_collect as news

class NewsRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def run_collector(self, search):
        root = Path(self.temp.name)
        with patch.object(news, 'OUT', root / 'news.json'), patch.object(news, 'STATUS', root / 'status.json'), patch.object(news, 'load_stocks', return_value=[{'code': '005930', 'name': '삼성전자'}]), patch.object(news, 'rss_search', side_effect=search), patch.object(news.time, 'sleep'):
            news.main()

    def test_total_outage_preserves_exact_previous_bytes_and_marks_failure(self):
        root = Path(self.temp.name)
        previous = b'{"previous": "keep"}\n'
        (root / 'news.json').write_bytes(previous)
        def fail(*a, **k):
            raise RuntimeError('HTTP 503')
        with self.assertRaises(RuntimeError):
            self.run_collector(fail)
        self.assertEqual((root / 'news.json').read_bytes(), previous)
        status = json.loads((root / 'status.json').read_text())
        self.assertEqual(status['status'], 'error')
        self.assertTrue(status['preserved_previous_data'])

    def test_successful_empty_search_is_not_an_outage(self):
        self.run_collector(lambda *a, **k: [])
        root = Path(self.temp.name)
        data = json.loads((root / 'news.json').read_text())
        self.assertEqual(data['stocks']['005930']['news_status'], 'no_articles')
        self.assertEqual(data['collection_status'], 'ok')
        self.assertEqual(json.loads((root / 'status.json').read_text())['status'], 'ok')

    def test_partial_search_is_reported(self):
        def search(*args, **kwargs):
            if args[1] == 'mt.co.kr':
                raise RuntimeError('HTTP 503')
            return []
        self.run_collector(search)
        data = json.loads((Path(self.temp.name) / 'news.json').read_text())
        self.assertEqual(data['collection_status'], 'partial')
        self.assertGreater(data['successful_queries'], 0)
        self.assertLess(data['successful_queries'], data['attempted_queries'])

    def test_service_outage_stops_after_three_stocks(self):
        with patch.object(news, 'load_stocks', return_value=[{'code': str(i), 'name': str(i)} for i in range(100)]), patch.object(news, 'rss_search', side_effect=RuntimeError('HTTP 503')) as search, patch.object(news.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                news.collect_payload()
            self.assertEqual(search.call_count, 6)

    def test_transient_503_retries_then_reads_response(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'<rss><channel/></rss>'
        error = urllib.error.HTTPError('https://news.google.com', 503, 'Unavailable', {}, None)
        with patch.object(news.urllib.request, 'urlopen', side_effect=[error, error, response]) as request, patch.object(news.time, 'sleep') as sleep:
            self.assertEqual(news.rss_search('삼성전자', 'mt.co.kr'), [])
            self.assertEqual(request.call_count, 3)
            self.assertEqual(sleep.call_count, 2)

    def test_permanent_403_does_not_retry(self):
        error = urllib.error.HTTPError('https://news.google.com', 403, 'Forbidden', {}, None)
        with patch.object(news.urllib.request, 'urlopen', side_effect=error) as request:
            with self.assertRaises(urllib.error.HTTPError):
                news.rss_search('삼성전자', 'mt.co.kr')
            self.assertEqual(request.call_count, 1)

if __name__ == '__main__':
    unittest.main()
