# Start TraderX v1.0

1. Open `/Users/ivanlopez/Desktop/traderx/TraderX.command` and keep its window open.
2. Open http://localhost:3000. System shows connection/data health; unavailable optional data does not stop the app.
3. Search an asset or use Scanner. Review its dated price, TraderX View, after-cost edge, uncertainty and opposing evidence.
4. Choose Paper Trade, enter a size, review the preview, then confirm PLACE PAPER ORDER. A preview is not a fill. Fresh later quotes, liquidity and session checks decide fills.
5. Check Portfolio and Orders. Add, trim or exit using a new preview. Evidence and journal history are captured automatically; notes are optional.
6. Keep the app and Mac awake to collect forward observations. Closing it creates a genuine evidence gap. It does not continuously train a language model.

## Credentials you may need

Existing `.env` and secrets were preserved. No new key is required merely to launch.

| Purpose | Configuration | Requirement |
|---|---|---|
| US equities/ETFs, news, historical and indicative options data | ALPACA_API_KEY, ALPACA_API_SECRET | Appropriate data entitlement; research SIP history and current IEX quotes are separate |
| Public crypto quotes/history | Coinbase public feed | No account key needed |
| Crypto funding context | Hyperliquid public information | No trading key needed |
| SEC filings | SEC_USER_AGENT | Identifying name and genuine contact email |
| Macro research | FRED_API_KEY | Optional |
| Energy observations | EIA_API_KEY | Optional |
| Local text extraction | LLM_PROVIDER=local, LOCAL_LLM_MODEL, LOCAL_LLM_BASE_URL | A separately running compatible local model; key only if its server requires one |
| Cloud text extraction | LLM_PROVIDER=openai, OPENAI_API_KEY, OPENAI_MODEL | Separately billed API access and a model present in config/llm_prices.json |

Leave paid automation/escalation off unless deliberately enabled. Default cloud limits are $1/day, $15/month and 10 calls/hour. Off mode makes zero LLM calls. Existing optional Coinbase account credentials can be checked read-only but are unnecessary for public data.

Do not paste credentials into chat or commit them. Update `.env` locally and restart. Never replace the real `.env` with `.env.example`. Old retired-provider fields may remain safely in your private file; v1 ignores them.

## What remains outside a finished software build

Historical data coverage, licenses/entitlements, independent elapsed forward observations and profitable model validation cannot be supplied by a software checkmark. Current models remain research-only until their frozen gates pass; some may never pass. Options are descriptive snapshot analytics, without options trading. Real-money execution is deliberately unavailable.

For installation from clean source, see README. For current verification results, see docs/AUTONOMOUS_ACCEPTANCE.md; docs/V1_FINAL_REPORT.md records the preceding cleanup.

## News and storage

Existing Alpaca credentials also supply news. System reports actual REST/stream access and observed article age. Collection runs before market open and throughout the session while TraderX stays running. News rules run locally and cost no LLM tokens. See docs/NEWS_INTELLIGENCE.md.

Use Git for source recovery. Do not duplicate the project, dependencies, archives or model data. Before a risky database migration, retain at most one temporary database-only backup, verify the migration and remove it. Never delete the active `.env`, `secrets/`, `data/traderx.db`, historical archives or research history.

## Autonomous research

Open Research → Autonomous Research. Review the conservative budgets, then Resume if you want periodic template research. Review new evidence proposes a bounded question; Run next executes a preregistered experiment. Pause stops numerical compute. Optional Director Local/Cloud also requires the matching enabled provider settings; no extra API is needed for templates.

New code proposals are review-only text and are never automatically executed. A successful backtest remains a challenger; use its scientific forward study workflow and the existing qualification requirements. See docs/AUTONOMOUS_RESEARCH.md. This phase has not been pushed or published.
