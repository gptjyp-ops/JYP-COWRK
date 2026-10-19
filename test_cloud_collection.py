"""Offline contract tests; no real credentials, broker or server required."""
import importlib.util
import os
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

try:
    import requests
except ImportError:
    requests = types.ModuleType('requests')
    requests.RequestException = RuntimeError
    requests.Session = Mock
    sys.modules['requests'] = requests

from stock_miner_cloud_client import CloudClient, KiwoomError, KST


def response(body, status=200, headers=None):
    return types.SimpleNamespace(status_code=status, json=lambda: body, headers=headers or {})


class CloudClientTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'KIWOOM_APP_KEY': 'fake-key', 'KIWOOM_SECRET_KEY': 'fake-secret'})
        env.start()
        self.addCleanup(env.stop)
        self.session = Mock()
        self.client = CloudClient(self.session)
        self.login = response({'return_code': 0, 'token': 'fake-token',
                               'expires_dt': (datetime.now(KST)+timedelta(hours=6)).strftime('%Y%m%d%H%M%S')})

    def test_token_is_reused_and_continuation_is_preserved(self):
        self.session.post.side_effect = [self.login, response({'return_code': 0, 'rows': []},
            headers={'cont-yn': 'Y', 'next-key': 'page2'}), response({'return_code': 0})]
        page = self.client.fetch_page(api_id='ka10035', path='/api/dostk/rkinfo', body={})
        self.assertEqual(page.continuation.next_key, 'page2')
        self.client.fetch_page(api_id='ka10035', path='/api/dostk/rkinfo', body={}, cont_yn='Y', next_key='page2')
        self.assertEqual(self.session.post.call_count, 3)
        headers = self.session.post.call_args.kwargs['headers']
        self.assertEqual(headers['next-key'], 'page2')
        self.assertEqual(headers['authorization'], 'Bearer fake-token')
        self.assertFalse(self.session.post.call_args.kwargs['allow_redirects'])

    def test_order_api_is_blocked_before_any_network_request(self):
        with self.assertRaises(KiwoomError):
            self.client.fetch_page(api_id='kt10000', path='/api/dostk/ordr', body={})
        self.session.post.assert_not_called()

    def test_ip_or_auth_failure_does_not_expose_response_secrets(self):
        self.session.post.return_value = response({'return_code': 1, 'return_msg': 'fake-secret fake-token'})
        with self.assertRaises(KiwoomError) as error:
            self.client.fetch_page(api_id='ka10035', path='/api/dostk/rkinfo', body={})
        self.assertNotIn('fake-secret', str(error.exception))
        self.assertNotIn('fake-token', str(error.exception))
        self.assertEqual(self.session.post.call_count, 1)

    def test_401_refreshes_token_once(self):
        self.session.post.side_effect = [self.login, response({}, 401), self.login, response({'return_code': 0})]
        self.client.fetch_page(api_id='ka10081', path='/api/dostk/chart', body={})
        self.assertEqual(self.session.post.call_count, 4)

    def test_bad_response_is_not_returned_as_market_data(self):
        self.session.post.side_effect = [self.login, response({'return_code': 7, 'return_msg': 'fake-secret'})]
        with self.assertRaises(KiwoomError) as error:
            self.client.fetch_page(api_id='ka10059', path='/api/dostk/stkinfo', body={})
        self.assertNotIn('fake-secret', str(error.exception))

    def test_missing_configuration_fails_before_clone(self):
        path = Path(__file__).parent / 'scripts/run_stock_miner_cloud.py'
        spec = importlib.util.spec_from_file_location('cloud_run', path)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with patch.dict(os.environ, {}, clear=True), patch.object(runner.subprocess, 'run') as run:
            with self.assertRaises(SystemExit) as error:
                runner.main()
            self.assertEqual(error.exception.code, 78)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
