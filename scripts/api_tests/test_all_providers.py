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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider_common import (ROOT, Reader, SafeError, config, safety_errors,
                             private_pem, require, validate_sec_contact, alpha_notice)

logging.disable(logging.CRITICAL)
PROVIDERS = ('OPENAI','ALPACA_PAPER','SEC_EDGAR','FRED','EIA','COINBASE_PUBLIC','COINBASE_ACCOUNT','HYPERLIQUID_PUBLIC')
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
        import httpx
        model=self.cfg['OPENAI_MODEL']
        require(bool(re.fullmatch(r'[a-z0-9][a-z0-9.-]{2,100}',model)), 'OPENAI_MODEL format is invalid')
        # Read-only metadata: no SDK dependency, text generation, or token charge.
        with httpx.Client(trust_env=False,timeout=25) as client:
            response=client.get('https://api.openai.com/v1/models/'+model,headers={'Authorization':'Bearer '+self.cfg['OPENAI_API_KEY']})
            require(response.status_code==200,'Configured model metadata unavailable')
            self.check('model metadata retrieved',response.json().get('id')==model,auth=True)
        return ('WORKING_READ_ONLY','Configured model metadata verified; no inference request or token charge')


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
        pem = private_pem(self.cfg, 'COINBASE_PRIVATE_KEY_PATH').decode('ascii')
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
    required &= set(PROVIDERS)
    selected = {x.strip() for x in args.only.split(',')} if args.only else set(PROVIDERS)
    if (required | selected) - set(PROVIDERS):
        print('Unknown provider ID; run --help or see API_SETUP.md')
        return 2
    if args.allow_billable_tests and cfg.get('ALLOW_BILLABLE_TESTS') != 'true':
        print('SAFETY_BLOCK: billable tests also require ALLOW_BILLABLE_TESTS=true')
        return 2
    methods = {'OPENAI': 'openai', 'ALPACA_PAPER': 'alpaca',  'SEC_EDGAR': 'sec',
               'FRED': 'fred', 'EIA': 'eia',
                'COINBASE_PUBLIC': 'coinbase_public',
               'COINBASE_ACCOUNT': 'coinbase_account', 'HYPERLIQUID_PUBLIC': 'hyperliquid', }
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
            record['model'] = cfg['OPENAI_MODEL']
            record['configured_endpoint'] = 'https://api.openai.com/v1/models/{model}'
        results.append(record)
        print(f'{provider:<23} {status:<27} {note}', flush=True)
    report = {'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'billable_tests_enabled': args.allow_billable_tests,
              'no_trading_routes': True, 'results': results}
    name = 'LAST_TEST_RESULTS.json' if not args.only else 'LAST_TARGETED_RESULTS.json'
    (ROOT / 'data').mkdir(exist_ok=True)
    (ROOT / 'data' / name).write_text(json.dumps(report, indent=2) + '\n')
    failed = any(r['required'] and r['status'] not in SUCCESS for r in results)
    print('\nRequired checks: ' + ('FAILED' if failed else 'PASS') + '; report: data/' + name)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
