#!/usr/bin/env python3
"""Live, read-only connectivity checks. Optional missing services do not fail the suite."""
from __future__ import annotations

import argparse
import base64
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider_common import (ROOT, Reader, SafeError, config, safety_errors,
                             private_path, require, validate_sec_contact)

logging.disable(logging.CRITICAL)
PROVIDERS = ('OPENAI', 'ALPACA_PAPER', 'ALPHA_VANTAGE', 'SEC_EDGAR', 'FRED', 'EIA',
             'X', 'KALSHI_PUBLIC_DEMO', 'KALSHI_DEMO', 'COINBASE_PUBLIC',
             'COINBASE_ACCOUNT', 'HYPERLIQUID_PUBLIC', 'GS_QUANT', 'INVO')
SUCCESS = {'WORKING', 'WORKING_READ_ONLY', 'WORKING_DEMO'}


class Probe:
    def __init__(self, cfg, allow_billable=False):
        self.cfg, self.allow_billable = cfg, allow_billable
        self.reader = Reader()
        self.checks = []
        self.auth = False

    def check(self, name, condition, auth=False):
        require(condition, name + ': response did not satisfy the expected schema')
        self.checks.append(name)
        if auth:
            self.auth = True

    def missing(self, *names):
        absent = [n for n in names if not self.cfg.get(n)]
        if absent:
            return ('NOT_CONFIGURED', 'Missing ' + ', '.join(absent))
        return None

    def openai(self):
        if self.cfg.get('LLM_PROVIDER') == 'off':
            return ('DISABLED', 'LLM_PROVIDER=off; no OpenAI requests made')
        missing = self.missing('OPENAI_API_KEY', 'OPENAI_MODEL')
        if missing:
            return missing
        from openai import OpenAI
        import httpx
        model = self.cfg['OPENAI_MODEL']
        require(bool(re.fullmatch(r'[a-z0-9][a-z0-9.-]{2,100}', model)), 'OPENAI_MODEL format is invalid')
        # Explicit origin; no OPENAI_BASE_URL override or financial data is sent.
        with OpenAI(api_key=self.cfg['OPENAI_API_KEY'], base_url='https://api.openai.com/v1',
                    http_client=httpx.Client(trust_env=False), timeout=25, max_retries=0) as client:
            data = client.models.retrieve(model)
            self.check('model metadata retrieved', data.id == model, auth=True)
            if not self.allow_billable:
                return ('REQUIRES_PAYMENT_APPROVAL', 'Authentication verified; response generation skipped by zero-spend policy')
            answer = client.responses.create(model=model, input='Reply with the single word OK.',
                                             max_output_tokens=16, store=False)
            self.check('text response generated', bool(answer.output_text.strip()))
        return ('WORKING', 'Configured model returned text; SDK ' + version('openai'))

    def alpaca(self):
        missing = self.missing('ALPACA_API_KEY', 'ALPACA_API_SECRET')
        if missing:
            return missing
        headers = {'APCA-API-KEY-ID': self.cfg['ALPACA_API_KEY'],
                   'APCA-API-SECRET-KEY': self.cfg['ALPACA_API_SECRET']}
        account = self.reader.request(self.cfg['ALPACA_TRADING_BASE_URL'] + '/v2/account', headers=headers)
        self.check('paper account metadata', bool(account.get('id')) and bool(account.get('status')), auth=True)
        bars = self.reader.request(self.cfg['ALPACA_DATA_BASE_URL'] + '/v2/stocks/AAPL/bars', headers=headers,
            params={'timeframe': '1Day', 'start': '2025-01-06T00:00:00Z',
                    'end': '2025-01-08T00:00:00Z', 'limit': 1, 'feed': 'iex'})
        self.check('historical IEX bar', bool(bars.get('bars')))
        quote = self.reader.request(self.cfg['ALPACA_DATA_BASE_URL'] + '/v2/stocks/AAPL/quotes/latest',
                                    headers=headers, params={'feed': 'iex'})
        self.check('IEX quote access', isinstance(quote.get('quote'), dict))
        return ('WORKING_DEMO', 'Paper account and IEX reads verified; SIP and options entitlements not verified')

    def alpha(self):
        missing = self.missing('ALPHA_VANTAGE_API_KEY')
        if missing:
            return missing
        require(self.cfg['ALPHA_VANTAGE_API_KEY'].lower() != 'demo', 'A shared demo key is not a configured personal credential')
        data = self.reader.request('https://www.alphavantage.co/query', params={
            'function': 'OVERVIEW', 'symbol': 'IBM', 'apikey': self.cfg['ALPHA_VANTAGE_API_KEY']})
        require(not any(x in data for x in ('Note', 'Information')), 'Quota or entitlement message returned; no data verified')
        self.check('IBM company overview', data.get('Symbol') == 'IBM' and bool(data.get('Name')), auth=True)
        return ('WORKING_READ_ONLY', 'One fundamentals request verified; other endpoint entitlements remain untested')

    def sec(self):
        missing = self.missing('SEC_USER_AGENT')
        if missing:
            return missing
        require(validate_sec_contact(self.cfg['SEC_USER_AGENT']), 'SEC_USER_AGENT needs an identifying name and contact email')
        headers = {'User-Agent': self.cfg['SEC_USER_AGENT'], 'Accept-Encoding': 'gzip, deflate'}
        data = self.reader.request('https://data.sec.gov/submissions/CIK0000320193.json', headers=headers)
        recent = data.get('filings', {}).get('recent', {})
        self.check('Apple submissions', bool(recent.get('accessionNumber')))
        facts = self.reader.request('https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json', headers=headers)
        self.check('Apple XBRL company facts', bool(facts.get('facts', {}).get('us-gaap')))
        forms = set(recent.get('form', []))
        for form in ('4', '10-K', '10-Q', '8-K'):
            self.check('form ' + form + ' metadata', form in forms)
        idx = recent['form'].index('10-K')
        accession = recent['accessionNumber'][idx].replace('-', '')
        filename = recent['primaryDocument'][idx]
        require(bool(re.fullmatch(r'[A-Za-z0-9_.-]+', filename)), 'Unexpected filing document path')
        filing = self.reader.request('https://www.sec.gov/Archives/edgar/data/320193/' + accession + '/' + filename,
                                     headers=headers, raw=True)
        self.check('10-K filing document retrieved', len(filing) > 1000 and '<' in filing)
        berkshire = self.reader.request('https://data.sec.gov/submissions/CIK0001067983.json', headers=headers)
        forms13 = berkshire.get('filings', {}).get('recent', {}).get('form', [])
        self.check('13F metadata from Berkshire filer', any(x.startswith('13F') for x in forms13))
        return ('WORKING_READ_ONLY', 'Submissions, XBRL, filing retrieval and all five requested form families verified')

    def fred(self):
        missing = self.missing('FRED_API_KEY')
        if missing:
            return missing
        params = {'series_id': 'FEDFUNDS', 'api_key': self.cfg['FRED_API_KEY'],
                  'file_type': 'json', 'limit': 1, 'sort_order': 'desc'}
        data = self.reader.request('https://api.stlouisfed.org/fred/series/observations', params=params)
        self.check('FEDFUNDS observation', bool(data.get('observations')), auth=True)
        vintage = self.reader.request('https://api.stlouisfed.org/fred/series/vintagedates', params=params)
        self.check('ALFRED vintage date', bool(vintage.get('vintage_dates')))
        point = dict(params, realtime_start='2020-01-01', realtime_end='2020-01-01')
        pit = self.reader.request('https://api.stlouisfed.org/fred/series/observations', params=point)
        self.check('point-in-time observation', bool(pit.get('observations')))
        return ('WORKING_READ_ONLY', 'FRED v1 observations, vintage dates and historical information date verified')

    def eia(self):
        missing = self.missing('EIA_API_KEY')
        if missing:
            return missing
        data = self.reader.request('https://api.eia.gov/v2/electricity/retail-sales/data/', params={
            'api_key': self.cfg['EIA_API_KEY'], 'frequency': 'monthly', 'data[0]': 'price',
            'facets[stateid][]': 'US', 'facets[sectorid][]': 'ALL',
            'sort[0][column]': 'period', 'sort[0][direction]': 'desc', 'length': 1})
        self.check('EIA v2 electricity price row', bool(data.get('response', {}).get('data')), auth=True)
        return ('WORKING_READ_ONLY', 'One monthly US electricity retail-price row verified')

    def x(self):
        if self.cfg.get('X_API_ENABLED') != 'true' or not self.allow_billable:
            return ('REQUIRES_PAYMENT_APPROVAL', 'REQUIRES_PAID_ACCESS; disabled under zero-spend policy')
        missing = self.missing('X_BEARER_TOKEN')
        if missing:
            return missing
        data = self.reader.request('https://api.x.com/2/tweets/search/recent',
            headers={'Authorization': 'Bearer ' + self.cfg['X_BEARER_TOKEN']},
            params={'query': '$AAPL -is:retweet', 'max_results': 10})
        self.check('recent search metadata', 'result_count' in data.get('meta', {}), auth=True)
        self.check('recent posts returned', bool(data.get('data')))
        return ('WORKING_READ_ONLY', 'Recent search verified; paid resources may have been consumed')

    def kalshi_public(self):
        base = self.cfg['KALSHI_BASE_URL']
        # An unfiltered demo listing can return a newly created combination whose
        # detail route is not available yet. Select an open standalone market.
        data = self.reader.request(base + '/markets',
                                   params={'limit': 1, 'status': 'open', 'mve_filter': 'exclude'})
        self.check('demo market listing', bool(data.get('markets')))
        ticker = data['markets'][0]['ticker']
        require(bool(re.fullmatch(r'[A-Za-z0-9_.-]+', ticker)), 'Unexpected demo market identifier')
        market = self.reader.request(base + '/markets/' + ticker)
        self.check('demo market details', market.get('market', {}).get('ticker') == ticker)
        book = self.reader.request(base + '/markets/' + ticker + '/orderbook')
        self.check('demo order book response', 'orderbook' in book or 'orderbook_fp' in book)
        return ('WORKING_DEMO', 'Public demo market listing, details and order-book schema; account auth not tested')

    def kalshi_account(self):
        missing = self.missing('KALSHI_API_KEY_ID')
        if missing:
            return missing
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.asymmetric import ed25519, rsa, padding
        key = serialization.load_pem_private_key(private_path(self.cfg, 'KALSHI_PRIVATE_KEY_PATH').read_bytes(), None)
        stamp = str(int(time.time() * 1000))
        path = '/trade-api/v2/portfolio/balance'
        msg = (stamp + 'GET' + path).encode()
        if isinstance(key, ed25519.Ed25519PrivateKey):
            signed = key.sign(msg)
        elif isinstance(key, rsa.RSAPrivateKey):
            signed = key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
        else:
            raise SafeError('Kalshi key must be Ed25519 or RSA')
        data = self.reader.request(self.cfg['KALSHI_BASE_URL'] + '/portfolio/balance', headers={
            'KALSHI-ACCESS-KEY': self.cfg['KALSHI_API_KEY_ID'], 'KALSHI-ACCESS-TIMESTAMP': stamp,
            'KALSHI-ACCESS-SIGNATURE': base64.b64encode(signed).decode()})
        self.check('authenticated demo balance schema', 'balance' in data, auth=True)
        return ('WORKING_DEMO', 'Demo balance read verified; amount and account identifiers omitted')

    def coinbase_public(self):
        data = self.reader.request('https://api.coinbase.com/api/v3/brokerage/market/products/BTC-USD')
        self.check('BTC-USD public product and price', data.get('product_id') == 'BTC-USD' and float(data.get('price', 0)) > 0)
        return ('WORKING_READ_ONLY', 'BTC-USD public market metadata and price; no account credential required')

    def coinbase_account(self):
        missing = self.missing('COINBASE_API_KEY_NAME')
        if missing:
            return missing
        from coinbase import jwt_generator
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        pem = private_path(self.cfg, 'COINBASE_PRIVATE_KEY_PATH').read_text()
        key = serialization.load_pem_private_key(pem.encode(), None)
        require(isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(key.curve, ec.SECP256R1),
                'Coinbase requires an ECDSA P-256 private key')
        def get(path):
            uri = jwt_generator.format_jwt_uri('GET', path)
            token = jwt_generator.build_rest_jwt(uri, self.cfg['COINBASE_API_KEY_NAME'], pem)
            return self.reader.request('https://api.coinbase.com' + path, headers={'Authorization': 'Bearer ' + token})
        permissions = get('/api/v3/brokerage/key_permissions')
        self.check('API permission metadata', 'can_view' in permissions, auth=True)
        require(permissions.get('can_view') is True and permissions.get('can_trade') is False
                and permissions.get('can_transfer') is False,
                'Coinbase credential must have view permission only; change permissions in CDP')
        self.check('view-only permission verified', True)
        data = get('/api/v3/brokerage/accounts')
        self.check('account metadata', isinstance(data.get('accounts'), list))
        return ('WORKING_READ_ONLY', 'View-only key and account-list schema verified; balances omitted')

    def hyperliquid(self):
        url = 'https://api.hyperliquid.xyz/info'
        def read(body):
            return self.reader.request(url, method='POST', body=body)
        meta = read({'type': 'meta'})
        self.check('perpetual metadata', bool(meta.get('universe')))
        mids = read({'type': 'allMids'})
        self.check('BTC mid price', float(mids.get('BTC', 0)) > 0)
        book = read({'type': 'l2Book', 'coin': 'BTC'})
        self.check('BTC order book', len(book.get('levels', [])) == 2 and any(book['levels']))
        # Public vault address in the official Info API documentation, not a user wallet.
        address = '0xdfc24b077bc1425ad1dea75bcb6f8158e10df303'
        fills = read({'type': 'userFills', 'user': address})
        self.check('public sample vault fills schema', isinstance(fills, list))
        portfolio = read({'type': 'portfolio', 'user': address})
        self.check('public sample vault portfolio', isinstance(portfolio, list) and bool(portfolio))
        return ('WORKING_READ_ONLY', 'Metadata, mids, book and public sample vault reads verified; fills may be empty')

    def gs_quant(self):
        import pandas as pd
        import gs_quant
        from gs_quant.timeseries.algebra import add
        series = pd.Series([100.0, 102.0, 104.0], index=pd.date_range('2025-01-01', periods=3))
        result = add(series, 5)
        self.check('standalone timeseries calculation', result.tolist() == [105.0, 107.0, 109.0])
        return ('WORKING', 'Local calculation verified without Goldman credentials; version ' + version('gs-quant'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', help='Comma-separated provider IDs')
    parser.add_argument('--required', help='Override REQUIRED_PROVIDERS for this invocation')
    parser.add_argument('--allow-billable-tests', action='store_true',
                        help='Only after spending approval: also requires ALLOW_BILLABLE_TESTS=true')
    args = parser.parse_args()
    cfg = config()
    errors = safety_errors(cfg)
    if errors:
        for err in errors:
            print('SAFETY_BLOCK: ' + err)
        return 2
    required = {x.strip() for x in (args.required if args.required is not None else cfg.get('REQUIRED_PROVIDERS', '')).split(',') if x.strip()}
    selected = {x.strip() for x in args.only.split(',')} if args.only else set(PROVIDERS)
    if (required | selected) - set(PROVIDERS):
        print('Unknown provider ID; run --help or see API_SETUP.md')
        return 2
    if args.allow_billable_tests and cfg.get('ALLOW_BILLABLE_TESTS') != 'true':
        print('SAFETY_BLOCK: billable tests also require ALLOW_BILLABLE_TESTS=true')
        return 2
    methods = {'OPENAI': 'openai', 'ALPACA_PAPER': 'alpaca', 'ALPHA_VANTAGE': 'alpha', 'SEC_EDGAR': 'sec',
               'FRED': 'fred', 'EIA': 'eia', 'X': 'x', 'KALSHI_PUBLIC_DEMO': 'kalshi_public',
               'KALSHI_DEMO': 'kalshi_account', 'COINBASE_PUBLIC': 'coinbase_public',
               'COINBASE_ACCOUNT': 'coinbase_account', 'HYPERLIQUID_PUBLIC': 'hyperliquid', 'GS_QUANT': 'gs_quant'}
    results = []
    for provider in PROVIDERS:
        if provider not in selected:
            continue
        probe = Probe(cfg, args.allow_billable_tests)
        try:
            if provider == 'INVO':
                status, note = 'NO_AUTHORIZED_API', 'No authorized public API identified; no automated extraction attempted'
            else:
                status, note = getattr(probe, methods[provider])()
        except SafeError as exc:
            status, note = 'FAILED', str(exc)
        except Exception as exc:
            status, note = 'FAILED', 'Local/SDK failure (' + type(exc).__name__ + '); sensitive error details suppressed'
        finally:
            probe.reader.close()
        record = {'provider': provider, 'status': status, 'diagnostic': note, 'checks_passed': probe.checks,
                  'authentication_verified': probe.auth, 'requests': probe.reader.receipts,
                  'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'required': provider in required}
        if provider == 'OPENAI':
            record['sdk_version'] = version('openai')
            record['model'] = cfg['OPENAI_MODEL']
            record['configured_endpoint'] = 'https://api.openai.com/v1/responses'
        results.append(record)
        print(f'{provider:<23} {status:<27} {note}', flush=True)
    report = {'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'billable_tests_enabled': args.allow_billable_tests,
              'no_trading_routes': True, 'results': results}
    name = 'LAST_TEST_RESULTS.json' if not args.only else 'LAST_TARGETED_RESULTS.json'
    (ROOT / 'docs' / name).write_text(json.dumps(report, indent=2) + '\n')
    failed = any(r['required'] and r['status'] not in SUCCESS for r in results)
    print('\nRequired checks: ' + ('FAILED' if failed else 'PASS') + '; report: docs/' + name)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
