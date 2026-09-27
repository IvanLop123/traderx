# API status — pre-build verification

Documentation checked: **2026-09-25 UTC**. Connectivity rerun during repository cleanup completed at **2026-09-25T17:27:20.105287+00:00**. Evidence: [actual results](LAST_TEST_RESULTS.json). This table reflects that full run; later reruns update the JSON.

**4 checks working; 8 credential/contact-dependent checks not configured; X disabled for cost; INVO has no identified authorized API.** No paid usage, account creation, terms acceptance, funding, orders or live execution occurred. The full requested account setup is not complete.

“Account created” refers only to this session; existing accounts elsewhere were not inspected. “Available” in the streaming/history columns means documented capability, not tested entitlement. “No key required” describes public access, not account authentication. No streaming session was tested.

| Provider / test ID | Purpose | Account created? | Credential configured? | Authentication verified? | Read test verified? | Streaming available? | Historical data available? | Sandbox/demo available? | Current access tier | Trading permission | Cost/free tier | Rate limit | Status | Blocker | Date verified UTC | Official docs URL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OPENAI | Financial text extraction later | No | No | No | No | Response streaming documented | Not a market-data source | No free inference sandbox established | Unknown | N/A | Billable inference disabled | Account/model dependent | NOT_CONFIGURED | Project key missing; generation also needs spending approval | 2026-09-25 | [Model](https://developers.openai.com/api/docs/models/gpt-5.4-nano) |
| ALPACA_PAPER | Equity/ETF and paper account reads | No | No | No | No | Equities/options documented | Yes, feed dependent | Paper | Unknown; IEX selected | All order calls absent | Basic free; no entitlement tested | Basic documented 200/min | REQUIRES_USER_ACTION | Paper login/signup and keys | 2026-09-25 | [Paper](https://docs.alpaca.markets/us/docs/paper-trading) |
| ALPHA_VANTAGE | Fundamentals, earnings, news | No | No | No | No | Not established | Endpoint dependent | Shared samples only | Unknown | N/A | Free key not obtained | Standard 25/day | REQUIRES_USER_ACTION | User registration/terms and personal key | 2026-09-25 | [API](https://www.alphavantage.co/documentation/) |
| SEC_EDGAR | Filings and XBRL | N/A | No contact supplied; no key needed | N/A | No | RSS; no WS established | Yes | No separate sandbox | Public | N/A | Free | 10/sec/user maximum | REQUIRES_USER_ACTION | Real identifying User-Agent name/contact email | 2026-09-25 | [Developer guidance](https://www.sec.gov/about/developer-resources) |
| FRED | Macro series and ALFRED vintages | No | No | No | No | No WS established | Yes, series/vintage dependent | No separate sandbox | Unknown | N/A | Free key | v1 120/min | REQUIRES_USER_ACTION | FRED login, API terms and key | 2026-09-25 | [API](https://fred.stlouisfed.org/docs/api/fred/) |
| EIA | Electricity and energy | No | No | No | No | No WS established | Dataset dependent | No separate sandbox | Public key registration pending | N/A | Free key | Guidance below 5/sec, ~9,000/hour | REQUIRES_USER_ACTION | Registration identity/email/terms and emailed key | 2026-09-25 | [API v2](https://www.eia.gov/opendata/documentation.php) |
| X | Social-market discussion | No | No; disabled | No | No | Paid HTTP stream | Recent/full archive by access | None established | No paid access | No writes implemented | Credits required for planned reads | Recent search app 450/15min | REQUIRES_PAYMENT_APPROVAL | REQUIRES_PAID_ACCESS; zero-spend instruction | 2026-09-25 | [Pricing](https://docs.x.com/x-api/getting-started/pricing) |
| KALSHI_PUBLIC_DEMO | Prediction-market demo data | N/A | No key required | N/A | Yes: list, details, book schema | Authenticated WS documented, untested | Documented, untested | Demo only | Public demo | Disabled | Free demo | Authenticated Basic: 200 tokens/sec; public quota not verified | WORKING_DEMO | None for tested public reads | 2026-09-25 | [Demo](https://docs.kalshi.com/getting_started/demo_env) |
| KALSHI_DEMO | Authenticated demo account | No | Local Ed25519 pair only; no registered ID | No | No | Auth required | Account/endpoint dependent | Demo only | Unknown | Disabled | Free demo | Account tier unverified | REQUIRES_USER_ACTION | Register public key in demo; save returned key ID | 2026-09-25 | [Keys](https://docs.kalshi.com/getting_started/api_keys) |
| COINBASE_PUBLIC | BTC/USD public data | N/A | No key required | N/A | Yes: product and positive price | Documented; untested | Candles documented; untested | Static mocks separately | Public product | Disabled | Tested read free | Numeric current limit unresolved | WORKING_READ_ONLY | None for tested public read | 2026-09-25 | [Product](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product) |
| COINBASE_ACCOUNT | View-only account metadata | No | No | No | No | Authenticated channels documented | Endpoint dependent | Static mocks only | Unknown | Required view-only key not yet supplied | No paid API read plan configured | Numeric current limit unresolved | REQUIRES_USER_ACTION | Optional CDP ECDSA view-only key/name and PEM | 2026-09-25 | [Authentication](https://docs.cdp.coinbase.com/coinbase-app/authentication-authorization/api-key-authentication) |
| HYPERLIQUID_PUBLIC | Crypto/perpetual and public-wallet research | N/A | No key required | N/A | Yes: metadata, mids, book, vault fills/portfolio schemas | Public WS documented; untested | Bounded by endpoint | Testnet exists; mainnet reads selected | Public Info | Disabled; no wallet created | Free tested reads | 1,200 weighted units/min/IP | WORKING_READ_ONLY | None for tested reads | 2026-09-25 | [Info](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint) |
| GS_QUANT | Standalone numerical utilities | N/A | No key required locally | N/A | Yes: import and arithmetic | Not a local-library feed | Only supplied data without entitlements | Local offline calculation | Open-source library | N/A | Free library | Local computation | WORKING | Hosted Goldman services excluded | 2026-09-25 | [Repository](https://github.com/goldmansachs/gs-quant) |
| INVO | Possible future manual/authorized imports | No | No | No | Not attempted | Unknown | Unknown | Unknown | No authorized API identified | No integration | Unknown | Unknown | NO_AUTHORIZED_API | NO_AUTHORIZED_AUTOMATED_API; exact 393TRADES association unverified | 2026-09-25 | [Official site](https://www.invoapp.com/) |

## Verification detail

- Nine actual external read requests succeeded: three Kalshi demo GETs, one Coinbase public GET and five Hyperliquid Info POST reads.
- GS Quant returned `[105.0, 107.0, 109.0]` from a supplied three-point series plus 5. This verifies local analytics only.
- Empty public-vault fills are accepted as a valid schema, not claimed as complete trading history. Kalshi order-book shape is checked; live liquidity is not inferred.
- No account-based provider has been authenticated in this session. Missing optional credentials produce `NOT_CONFIGURED` in the runner and user-action blockers above.
- OpenAI model default: `gpt-5.4-nano`; intended response endpoint: `https://api.openai.com/v1/responses`; SDK installed: `openai 3.19.2`. No OpenAI request was made.
- Installed direct packages: `alpaca-py 0.44.0`, `gs-quant 2.1.17`, `coinbase-advanced-py 1.8.4`, `httpx 0.28.1`, `python-dotenv 1.2.3`, `cryptography 50.0.1`, `PyJWT 2.15.0`. Python 3.12.14. Full versions are pinned in `requirements.lock.txt`.
- Environment validation and dependency compatibility checks passed. Eleven offline safety/repository tests passed; these are separate from live connectivity results.
- Secrets have owner-only permissions. Git is initialized locally on `main`. The protected paths are ignored and untracked; safe project files are staged for an initial commit. Local candidate and staged-content scans found no exposed credentials. No remote, commit or push was created.

## Remaining actions in priority order

1. Supply SEC identification to unlock keyless SEC tests.
2. Obtain free paper Alpaca, Alpha Vantage, FRED and EIA keys through their own signup/verification steps.
3. Register the generated Kalshi public key in a demo account and save its ID.
4. Optionally provide a Coinbase view-only CDP key; its public data already works.
5. Leave OpenAI generation and X disabled unless you later authorize spending. INVO requires official authorization/documentation before any API work.

Exact links and storage fields: [API_SETUP.md](API_SETUP.md). Pricing and licensing uncertainty: [API_COSTS_AND_LIMITS.md](API_COSTS_AND_LIMITS.md). Full provider research: [API_CAPABILITIES.md](API_CAPABILITIES.md).

## Cleanup correction

An initial cleanup run listed a Kalshi demo combination market successfully, but
its individual detail request returned HTTP 404. The check now selects an open
standalone market with the documented `status=open` and `mve_filter=exclude`
filters. The subsequent complete suite passed the listing, detail and order-book
checks. This fixes test sample selection; it does not weaken response validation
or claim account authentication. [Official listing filters](https://docs.kalshi.com/api-reference/market/get-markets).
