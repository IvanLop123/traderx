# Provider implementation references

Official documentation was checked during the September 25, 2026 build. Phase 0
remains independently testable with `./test_apis.command`; its JSON receipts are
actual connectivity evidence. Mocks test normalization/error handling, not real
credentials or paid entitlements.

| Adapter | Official source | Current application behavior |
|---|---|---|
| Coinbase public | https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles | Exchange ticker/daily candles; no key; three-year history paginated in batches ≤290 bars |
| Hyperliquid | https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint | Read-only Info POSTs for context, fills and portfolio; no exchange endpoint |
| Kalshi | https://docs.kalshi.com/api-reference/market/get-markets | Public demo open standalone markets; settlement rules retained in source |
| Alpaca | https://docs.alpaca.markets/us/reference/stockbars | Credentialed latest quotes and stock bars, IEX default, raw corporate-action adjustment, bounded pagination |
| Alpha Vantage | https://www.alphavantage.co/documentation/ | NEWS_SENTIMENT, EARNINGS_CALL_TRANSCRIPT, HISTORICAL_OPTIONS; entitlement errors visible |
| SEC | https://www.sec.gov/search-filings/edgar-application-programming-interfaces | Submissions and archive read helper; real contact required; paced below SEC ceiling |
| FRED / ALFRED | https://fred.stlouisfed.org/docs/api/fred/series_observations.html | Explicit realtime_start/end vintage; publication/observed time remains separate |
| EIA | https://www.eia.gov/opendata/documentation.php | Electricity retail-sales API v2 |
| X | https://docs.x.com/x-api/posts/search-recent-posts | Bearer recent search; disabled by default; requires paid account access |
| LM Studio | https://lmstudio.ai/docs/developer/openai-compat | Loopback /models and /chat/completions; optional authentication |
| OpenAI | https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create | Text-only structured JSON with output token cap; no tools; no retries |
| GS Quant | Phase 0 API_CAPABILITIES.md and current local SDK smoke test | Optional local analytics; not an institutional dependency |

Network requests use finite timeouts, no environment proxy inheritance and no
redirects. Provider retries apply only to read-only 5xx responses; 429 defers work.
Status distinguishes NOT_CONFIGURED, DISABLED, NOT_CHECKED, WORKING_READ_ONLY,
WORKING_DEMO, DEGRADED, RATE_LIMITED and ERROR. Unexpected data shapes are degraded,
not silently replaced by synthetic values. Raw responses and source URLs persist;
authentication headers and API-key query parameters are never persisted.

The public worker polls three spot symbols every minute and context hourly.
`config/ingestion.json` controls independent credentialed schedules: Alpaca quotes
every minute and daily history, SEC every 30 minutes, Alpha Vantage news every six
hours, FRED every six hours, and EIA daily. Missing keys start no provider task.
Next-run times persist across restarts. SEC primary documents are deduplicated;
bounded narrative sections and deterministic Form 4 parsing retain source links.
Premium transcripts/options and X reads are explicit. Native venue streaming
subscriptions remain future integration work.

Alpaca latest quotes were checked against the official endpoint documentation:
https://alpaca.markets/learn/latest-trade-quote . Midpoint is labelled as a quote
midpoint, not a last trade. Daily volume used in paper participation checks is
labelled with its source bar; absent volume fails risk closed.
