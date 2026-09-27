"""Read-only provider bootstrap helpers. Never log request bodies, URLs with keys, or exceptions."""
from __future__ import annotations

import os
import re
import stat
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SAFE_SETTINGS = {
    'ENABLE_LIVE_TRADING': 'false',
    'ALPACA_TRADING_MODE': 'paper',
    'ALPACA_TRADING_BASE_URL': 'https://paper-api.alpaca.markets',
    'ALPACA_DATA_BASE_URL': 'https://data.alpaca.markets',
    'ALPACA_DATA_FEED': 'iex',
    'KALSHI_ENV': 'demo',
    'KALSHI_BASE_URL': 'https://external-api.demo.kalshi.co/trade-api/v2',
    'KALSHI_TRADING_ENABLED': 'false',
    'COINBASE_TRADING_ENABLED': 'false',
    'HYPERLIQUID_NETWORK': 'mainnet',
    'HYPERLIQUID_TRADING_ENABLED': 'false',
}
KEY_GROUPS = {
    'OPENAI': ['OPENAI_API_KEY'],
    'ALPACA_PAPER': ['ALPACA_API_KEY', 'ALPACA_API_SECRET'],
    'ALPHA_VANTAGE': ['ALPHA_VANTAGE_API_KEY'],
    'SEC_EDGAR': ['SEC_USER_AGENT'],
    'FRED': ['FRED_API_KEY'],
    'EIA': ['EIA_API_KEY'],
    'X': ['X_BEARER_TOKEN'],
    'KALSHI_DEMO': ['KALSHI_API_KEY_ID'],
    'COINBASE_ACCOUNT': ['COINBASE_API_KEY_NAME'],
}


class SafeError(Exception):
    """Only explicitly authored, non-sensitive diagnostic text belongs here."""


def config():
    defaults = dotenv_values(ROOT / '.env.example', interpolate=False)
    local = dotenv_values(ROOT / '.env', interpolate=False)
    return {k: os.environ.get(k, local.get(k, v) or '') for k, v in defaults.items()}


def safety_errors(cfg):
    return [f'{k} must equal its safe default' for k, v in SAFE_SETTINGS.items() if cfg.get(k) != v]


def validate_sec_contact(value):
    return bool(re.fullmatch(r'[^\r\n]+\s+[^\s@]+@[^\s@]+\.[^\s@]+', value or ''))


def private_path(cfg, setting):
    raw = Path(cfg.get(setting, ''))
    p = raw if raw.is_absolute() else ROOT / raw
    if p.is_symlink():
        raise SafeError(f'{setting}: symbolic links are not accepted')
    p = p.resolve()
    if not p.is_relative_to((ROOT / 'secrets').resolve()):
        raise SafeError(f'{setting}: file must be inside TraderX/secrets')
    if not p.is_file():
        raise SafeError(f'{setting}: private key file is missing')
    if os.name != 'nt' and stat.S_IMODE(p.stat().st_mode) & 0o077:
        raise SafeError(f'{setting}: restrict permissions to owner only')
    return p


# Restrict every network call to these specific read operations. POST /info is
# Hyperliquid's documented read API. No exchange, order, transfer or funding routes.
READ_ROUTES = {
    'paper-api.alpaca.markets': r'/v2/account',
    'data.alpaca.markets': r'/v2/stocks/AAPL/(bars|quotes/latest)',
    'www.alphavantage.co': r'/query',
    'data.sec.gov': r'/(submissions/CIK\d{10}\.json|api/xbrl/companyfacts/CIK\d{10}\.json)',
    'www.sec.gov': r'/Archives/edgar/data/\d+/\d+/[A-Za-z0-9_.-]+',
    'api.stlouisfed.org': r'/fred/series/(observations|vintagedates)',
    'api.eia.gov': r'/v2/electricity/retail-sales/data/',
    'external-api.demo.kalshi.co': r'/trade-api/v2/(markets(?:/[A-Za-z0-9_.-]+(?:/orderbook)?)?|portfolio/balance)',
    'api.coinbase.com': r'/api/v3/brokerage/(market/products/BTC-USD|accounts|key_permissions)',
    'api.hyperliquid.xyz': r'/info',
    'api.x.com': r'/2/tweets/search/recent',
}
INFO_TYPES = {'meta', 'allMids', 'l2Book', 'userFills', 'portfolio'}


def authorize_request(method, url, body=None):
    parsed = urlsplit(url)
    pattern = READ_ROUTES.get(parsed.hostname)
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port
            or parsed.query or parsed.fragment or not pattern or not re.fullmatch(pattern, parsed.path)):
        raise SafeError('Network safety guard rejected the destination')
    if parsed.hostname == 'api.hyperliquid.xyz':
        if method != 'POST' or not isinstance(body, dict) or body.get('type') not in INFO_TYPES:
            raise SafeError('Only allowlisted Hyperliquid Info reads are permitted')
    elif method != 'GET':
        raise SafeError('Only GET is permitted for this provider')


class Reader:
    def __init__(self):
        self.client = httpx.Client(timeout=25, follow_redirects=False, trust_env=False)
        self.last = {}
        self.receipts = []

    def close(self):
        self.client.close()

    def request(self, url, *, method='GET', params=None, headers=None, body=None, raw=False):
        authorize_request(method, url, body)
        host = urlsplit(url).hostname
        # Conservative host pacing, including SEC well below its 10/s ceiling.
        time.sleep(max(0, 1.1 - (time.monotonic() - self.last.get(host, 0))))
        self.last[host] = time.monotonic()
        receipt = {'method': method, 'endpoint': url, 'http_status': None}
        self.receipts.append(receipt)
        try:
            res = self.client.request(method, url, params=params, headers=headers, json=body)
            receipt['http_status'] = res.status_code
        except httpx.RequestError:
            raise SafeError('Network/TLS connection failed; no credentials or response body logged') from None
        if res.status_code != 200:
            labels = {401: 'authentication rejected', 403: 'access or entitlement denied',
                      429: 'rate limited; wait before retrying'}
            raise SafeError(f'HTTP {res.status_code}: {labels.get(res.status_code, "read request failed")}')
        if raw:
            return res.text
        try:
            result = res.json()
        except ValueError:
            raise SafeError('Expected JSON but received a different response format') from None
        if isinstance(result, dict) and any(k in result for k in ('error', 'error_code', 'Error Message')):
            raise SafeError('Provider returned an error object; body omitted for privacy')
        return result


def require(condition, message):
    if not condition:
        raise SafeError(message)
