# Provider capabilities

Checked 2026-09-25 UTC. “Documented” is not an assertion that an account entitlement has been verified. Actual successful checks are in `LAST_TEST_RESULTS.json`; streaming was researched but no persistent stream was opened. This bootstrap does not implement strategies, trading, signals or historical ingestion.

## OpenAI

Documented `gpt-5.4-nano` supports text, structured output and response streaming, suitable as an inexpensive configurable extraction starting point. It is not a licensed market-data feed or historical transcript source. Account/model access and response generation are **unverified**. No separate free simulation of model inference was identified. Authentication is a bearer API key at `https://api.openai.com/v1`. [Model and capabilities](https://developers.openai.com/api/docs/models/gpt-5.4-nano).

## Alpaca

Documented equities/ETF bars, quotes, trades and WebSockets; options feeds depend on subscription. Paper account metadata can be retrieved separately from market data. Basic equities use real-time IEX, not full-market SIP; options Basic uses indicative data rather than OPRA. Planned read checks cover a paper account, an older IEX bar and an IEX quote. **No account entitlement is verified yet**, including SIP, options or paid plan access. [Data plans](https://docs.alpaca.markets/us/docs/about-market-data-api), [paper-only accounts](https://docs.alpaca.markets/us/docs/paper-trading).

REST roots: `https://paper-api.alpaca.markets` and `https://data.alpaca.markets`. Authentication uses `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY` headers. No order method exists in the bootstrap. [Authentication and feeds](https://docs.alpaca.markets/us/docs/market-data-faq).

## Alpha Vantage

REST endpoint: `https://www.alphavantage.co/query`, with `apikey` query authentication. Documented functions include:

| Need | Function | Account access here |
|---|---|---|
| Earnings transcripts | `EARNINGS_CALL_TRANSCRIPT` | Unknown; no personal key |
| Fundamentals | `OVERVIEW`, financial statements | Unknown; overview smoke test prepared |
| Earnings history | `EARNINGS` | Unknown |
| Insider transactions | `INSIDER_TRANSACTIONS` | Unknown |
| Institutional holdings | `INSTITUTIONAL_HOLDINGS` | Unknown |
| Options | `HISTORICAL_OPTIONS`, `REALTIME_OPTIONS` | Premium; unconfigured |
| News/sentiment | `NEWS_SENTIMENT` | Unknown |

No dedicated sandbox or supported streaming interface was established from the reviewed REST documentation. Shared demo samples do not prove personal entitlement. [Official functions and premium markers](https://www.alphavantage.co/documentation/).

## SEC EDGAR

Public submissions, XBRL company facts and filing documents; no API key. Requests require responsible identification. Company submissions include form/accession metadata; Form 4, 10-K, 10-Q and 8-K can be selected by form. For 13F use the institutional manager's CIK, not the stock issuer's CIK. Tests use Apple plus Berkshire's manager filings, but remain blocked on the user's identifying User-Agent. [JSON APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [filing access and indexes](https://www.sec.gov/about/developer-resources).

Roots: `https://data.sec.gov` for JSON and `https://www.sec.gov/Archives` for filings. Historical access exists; there is no separate sandbox or documented WebSocket feed in these APIs. RSS and indexes support later polling. Preserve accession, acceptance and filing dates in any future point-in-time work. [Developer resources](https://www.sec.gov/about/developer-resources).

## FRED / ALFRED

The prepared tests deliberately use supported **FRED API v1**, `https://api.stlouisfed.org/fred`, with a 32-character `api_key` query parameter. It covers observations, vintage dates and a historical information date. ALFRED is accessed by specifying `realtime_start`, `realtime_end` or vintage dates in the same API; do not treat today's revised series as historical knowledge. [API key](https://fred.stlouisfed.org/docs/api/api_key.html), [observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html), [real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html).

Version 2 also exists for release-level retrieval and uses bearer-header authentication. It was researched but is not implemented here; v1 fits these small series/vintage checks. No WebSocket or separate sandbox was established. Series may represent rates, prices, employment or output and have different release schedules. [Version 2](https://fred.stlouisfed.org/docs/api/fred/v2/), [v2 authentication](https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html).

## EIA

Use `https://api.eia.gov/v2/` and `api_key` query authentication. The prepared read asks for a single US monthly electricity retail-price row. Later dataset candidates: electricity retail sales; plant/fuel generation; electricity operating data for demand and generation by energy source; nuclear/uranium information. Discover exact available routes/facets and units through v2 metadata before ingestion. Release lag and history differ by series; no real-time market-price guarantee. No separate sandbox or WebSocket interface was established. [v2 documentation](https://www.eia.gov/opendata/documentation.php), [nuclear/uranium](https://www.eia.gov/nuclear/).

## X

Use app-only OAuth 2 bearer authentication to read `https://api.x.com/2`. Planned search supports ticker/cashtag research subject to operator access. Recent search covers seven days; full-archive access is paid. User timelines are separate read endpoints. [Search](https://docs.x.com/x-api/posts/search/introduction), [endpoint limits](https://docs.x.com/x-api/fundamentals/rate-limits).

Filtered streaming is an HTTP stream, not a WebSocket. Pay-per-use documentation lists one connection and 1,000 rules; semantic embedding operators require the specified Enterprise access. No free market-monitoring entitlement or sandbox was verified. All actual X reads are disabled. [Filtered stream](https://docs.x.com/x-api/posts/filtered-stream/introduction).

## Kalshi

Public **demo** market list, details and order-book response schema passed. Demo data may differ substantially from live markets; an empty demo book is possible. Authenticated demo account/balance access remains unverified until the local key's public half is registered and the returned ID is supplied. [Demo environment](https://docs.kalshi.com/getting_started/demo_env).

The client supports Ed25519 and RSA-PSS/SHA-256 signatures, signs timestamp + method + path without query parameters, and uses Kalshi's three access headers. No production host is allowed. [Authentication](https://docs.kalshi.com/getting_started/api_keys).

Documented REST and authenticated WebSocket interfaces cover market data. Historical/candlestick endpoints are available separately; depth and retention were not tested. No order or funding access was exercised. [Market API](https://docs.kalshi.com/api-reference/market/get-markets).

## Coinbase Advanced Trade / CDP

Public BTC-USD product metadata and positive market price passed without a key at `https://api.coinbase.com/api/v3/brokerage/market/products/BTC-USD`. Authenticated account metadata is separate and **unverified**. [Public product](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product).

CDP API key names plus ECDSA P-256 private PEM generate short-lived JWTs. This Coinbase App integration uses ECDSA/ES256, not older Coinbase Pro passphrases. Prepared private checks first require `can_view=true`, `can_trade=false`, `can_transfer=false`, then read accounts. [Key setup](https://docs.cdp.coinbase.com/coinbase-app/authentication-authorization/api-key-authentication), [permissions](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/data-api/get-api-key-permissions).

REST product data, candles and WebSocket market channels are documented. The separate Advanced Trade sandbox returns static mocked responses and cannot establish real account entitlements or live-market behavior. Historical coverage and stream limits were not verified against an account. [REST](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/rest-api), [sandbox](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/sandbox).

## Hyperliquid

The unauthenticated mainnet Info API at `https://api.hyperliquid.xyz/info` passed metadata, BTC mid price, BTC book and public sample-vault fills/portfolio reads. The vault is a public example from the official docs; no user wallet was created or accessed. Empty fills do not prove unavailable authentication, and historical samples do not establish complete lifetime performance. Other documented Info reads include positions, orders, funding and candles; only the reported checks were executed. [Info API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint).

Public WebSockets and a separate testnet exist. The chosen mainnet connection is read-only. No private wallet key, execution wallet or exchange endpoint is present. Retention and per-response limits vary, so later bulk historical work requires additional design. [API overview](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api), [limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits).

## Goldman Sachs GS Quant

Installed and imported; local time-series arithmetic produced the expected result without authentication or network data. Standalone numerical utilities can operate on user-supplied data. The library does not supply free institutional Goldman market data. Marquee datasets, remote pricing and other entitled services require sessions/permissions and are outside this setup. [Official library](https://github.com/goldmansachs/gs-quant), [standalone arithmetic](https://developer.gs.com/docs/gsquant/api/functions/gs_quant.timeseries.algebra.add.html), [entitled dataset access](https://developer.gs.com/docs/gsquant/data/accessing-data/querying-data/).

## INVO / 393TRADES

Reviewed the [official Invo trading site](https://www.invoapp.com/) and searched for authorized developer documentation. No suitable official public API was identified. This is an absence-of-evidence finding, not proof that private partner APIs do not exist. The exact relationship of the name “393TRADES” to this site was not established. Similarly named invoicing/gaming APIs are unrelated. Status: `NO_AUTHORIZED_API` / `NO_AUTHORIZED_AUTOMATED_API`. No app scraping, private endpoint inspection or automated extraction was attempted. Future options are manual import, user-provided CSV, or explicitly authorized API access.

## Permitted use and future distribution

These are documented developer read interfaces used for private connectivity checks. Connectivity does not grant redistribution, commercial-display or model-training rights. A future public/commercial TraderX product has not been licensed by this bootstrap. In particular, Alpha Vantage's terms describe personal/noncommercial use and require contact for commercial use; EIA permits data retrieval/analysis with attribution; FRED data may carry third-party restrictions; Goldman source licensing does not convey dataset entitlements. Account services remain subject to the agreements the user accepts. [Alpha Vantage terms](https://www.alphavantage.co/terms_of_service/), [EIA terms on registration](https://www.eia.gov/opendata/register.php), [FRED terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html), [GS Quant license](https://github.com/goldmansachs/gs-quant).
