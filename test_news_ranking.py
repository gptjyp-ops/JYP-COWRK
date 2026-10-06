import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import news_collect as news

class NewsRankingTests(unittest.TestCase):
    def test_first_seen_survives_repeated_and_duplicate_headlines(self):
        previous=[{'title':'스피어 공급계약 - 머니투데이', 'first_seen_at':'2026-10-06T00:00:00+00:00'}]
        items=[{'title':'스피어 공급계약 - 연합뉴스', 'published':'2026-10-06T01:00:00+00:00'}, {'title':'스피어 공급계약 - 머니투데이', 'published':'2026-10-06T00:00:00+00:00'}]
        found=news.track_articles(items,previous,'2026-10-06T02:00:00+00:00')
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['first_seen_at'],previous[0]['first_seen_at'])

    def test_watch_refresh_uses_public_queries_and_preserves_other_stocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'news.json'
            out.write_text(json.dumps({'generated_at':'2026-10-01T00:00:00+00:00','stocks':{'other':{'name':'keep'}},'themes':[{'id':'keep'}]}))
            with patch.object(news,'OUT',out),patch.object(news,'load_watchlist',return_value=[{'name':'스피어','code':'347700'},{'name':'디케이락','code':'105740'}]),patch.object(news,'rss_search',return_value=[]) as search,patch.object(news.time,'sleep'):
                result=news.collect_payload(watch_only=True)
            self.assertEqual(search.call_count,2*len(news.PUBLIC_NEWS_QUERIES))
            self.assertTrue(all(call.args[0] in news.PUBLIC_NEWS_QUERIES for call in search.call_args_list))
            self.assertEqual(result['stocks']['other']['name'],'keep')
            self.assertEqual(result['themes'],[{'id':'keep'}])
            self.assertEqual(result['generated_at'],'2026-10-01T00:00:00+00:00')
            self.assertIn('watch_checked_at',result)

if __name__=='__main__':
    unittest.main()
