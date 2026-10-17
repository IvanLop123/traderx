"""Offline guard checks; these never contact providers or produce connectivity PASS records."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider_common import SafeError, SAFE_SETTINGS, authorize_request, safety_errors
from test_all_providers import Probe


class GuardTests(unittest.TestCase):
    def test_rejects_orders_transfers_and_unknown_hosts(self):
        for method, url in [
            ('POST', 'https://paper-api.alpaca.markets/v2/orders'),
            ('GET', 'https://api.alpaca.markets/v2/account'),
            ('GET', 'https://external-api.kalshi.com/trade-api/v2/portfolio/balance'),
            ('POST', 'https://api.coinbase.com/api/v3/brokerage/orders'),
            ('POST', 'https://api.hyperliquid.xyz/exchange'),
            ('GET', 'https://api.coinbase.com.evil.test/api/v3/brokerage/accounts'),
            ('GET', 'http://api.coinbase.com/api/v3/brokerage/accounts'),
            ('GET', 'https://user:pass@api.coinbase.com/api/v3/brokerage/accounts'),
        ]:
            with self.subTest(url=url), self.assertRaises(SafeError):
                authorize_request(method, url)

    def test_hyperliquid_only_info_types(self):
        authorize_request('POST', 'https://api.hyperliquid.xyz/info', {'type': 'meta'})
        with self.assertRaises(SafeError):
            authorize_request('POST', 'https://api.hyperliquid.xyz/info', {'type': 'order'})

    def test_live_flags_fail_closed(self):
        self.assertEqual(safety_errors(dict(SAFE_SETTINGS)), [])
        for name in SAFE_SETTINGS:
            changed = dict(SAFE_SETTINGS, **{name: 'unsafe'})
            self.assertTrue(safety_errors(changed))


    def test_empty_public_data_is_not_success(self):
        probe = Probe({})
        try:
            with patch.object(probe.reader, 'request', return_value={'product_id': 'BTC-USD'}):
                with self.assertRaises(SafeError):
                    probe.coinbase_public()
        finally:
            probe.reader.close()

    def test_missing_keys_do_not_call_network(self):
        probe = Probe({})
        try:
            with patch.object(probe.reader, 'request', side_effect=AssertionError('No network expected')):
                for method in ('openai', 'alpaca', 'sec', 'fred', 'eia', 'coinbase_account'):
                    self.assertEqual(getattr(probe, method)()[0], 'NOT_CONFIGURED')
        finally:
            probe.reader.close()


if __name__ == '__main__':
    unittest.main()
