# TraderX

Local quantitative research and a paper-trading simulator, with optional text AI.
This is the original permanent repository at `/Users/ivanlopez/Desktop/TraderX`.
Phase 0 checks and private configuration have been preserved. Nothing was pushed.

## Open the app

Double-click `TraderX.command`, or run:

```sh
cd /Users/ivanlopez/Desktop/TraderX
./TraderX.command
```

- Dashboard: http://localhost:3000
- Backend health: http://localhost:8000/api/v1/health
- Interactive API docs: http://localhost:8000/docs

The launcher builds the production UI when sources change. `dev.command` is also
available for development with automatic frontend reloads.

Keep the launch window open. Ctrl-C stops only processes that launcher started.
The local default stores data in `data/traderx.db` (SQLite). PostgreSQL is supported
through `DATABASE_URL`; all migrations and a separate PostgreSQL integration test
were exercised. Redis publishes updates when available; database jobs survive its
absence. Backend and frontend bind only to loopback. This is a single-user local
app, not an authenticated public deployment.

## What works

- Real public Coinbase spot quotes and completed daily candles; Hyperliquid
  perpetual context/public wallet reads; Kalshi public demo markets.
- Read adapters for credentialed Alpaca history, Alpha Vantage news/transcripts/
  options, SEC filing metadata and documents, FRED vintage observations, EIA
  electricity and explicitly enabled X access. Missing accounts remain visible.
- Raw response provenance, normalized events, durable bars, features, signals,
  documents, text jobs, research results, model versions and execution records.
- Local returns, volume, volatility, VWAP, ATR, RSI, MACD, regime features;
  deterministic Form 4/13F parsing, narrative keyword evidence, thematic mentions,
  trader metrics, European option Greeks, parity and probability research utilities.
- Source-backed transcript period comparisons, observed insider clusters and
  amendment gates, same-quarter institutional holdings comparisons, historical
  options liquidity/IV/skew summaries, and expiring evidence features.
- Lagged momentum simulation with next-bar execution and costs; chronological
  ridge/logistic/volatility baselines; validation calibration; purged holdout;
  fixed strategy comparison, walk-forward checks, cost stress and benchmark gates;
  portable saved coefficients; point-in-time joins for optional numeric evidence.
- Internal paper cash/positions/fees, persisted risk approvals, duplicate guards,
  stale-feed checks, concentration limits and a kill switch. Live execution is
  unavailable. There is no broker order-submission route.
- Next.js dashboard, scanner, asset detail, evidence drawer, intelligence views,
  research controls, portfolio, orders, risk, health, AI settings and explicit chat.

This is a working research baseline, **not the entire requested main build**.
Read [build coverage and remaining engineering](docs/BUILD_STATUS.md) before using
any subsystem as if it were fully validated.

## Optional AI

No OpenAI key, SDK or model server is needed to start or use quantitative modules.
`LLM_PROVIDER=off` is the safe default. Automated analysis and cloud escalation
are off. In Settings choose AI Off, Local AI, OpenAI or Hybrid. UI choices persist
in the database while the environment is unchanged. Deliberate AI configuration
changes in `.env` take effect on restart; credentials remain in `.env`.

For LM Studio, load a compatible text model, start its OpenAI-compatible server
on port 1234, then enter the exact model identifier in Settings. Local keys are
optional. No model is downloaded or trained by TraderX. A later fine-tuned model
can use the same contract and a new model identifier or prompt revision.

OpenAI defaults: $1/day, $15/month, 10 requests/hour, 1,200 output tokens/request.
Unknown model pricing blocks cloud calls. Local calls cost $0 in external API fees.
Requests with uncertain outcomes keep conservative reservations and are not
retried automatically. See [AI architecture](docs/AI_ARCHITECTURE.md).

## Installation and verification

The existing Python 3.12 virtual environment is retained. A fresh app-only setup:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-app.txt
npm ci --prefix frontend --cache data/npm-cache
.venv/bin/python -m alembic upgrade head
./TraderX.command
```

For the complete existing Phase 0 environment use `requirements.lock.txt`.
`requirements-openai.txt` is only needed for the optional legacy SDK smoke test;
the application itself uses HTTPX. Never replace your existing `.env` with the
example. New safe defaults are read from `.env.example` when absent locally.

```sh
./test.command                       # running app needed for frontend HTTP tests
./check_environment.command          # original environment/security check
./test_apis.command                  # original free, read-only provider checks
npm run build --prefix frontend       # production build/type validation
```

The browser workflows were also tested manually in a browser. Tests use
artificial fixtures only in isolated test databases. Production pages show real
observations or explicit empty/unavailable states.

## Docker / PostgreSQL

Compose defines PostgreSQL, Redis, backend and frontend. Set a URL-safe local
`TRADERX_DATABASE_PASSWORD` in your shell, then `docker compose up --build`.
No database/Redis port is published; UI/backend ports bind to loopback. Docker was
not installed on the development Mac, so Compose execution is not verified.
Native PostgreSQL migrations and transaction tests passed independently.

For an existing PostgreSQL instance set `DATABASE_URL` in `.env` to your local
SQLAlchemy `postgresql+psycopg://...` URL and run migrations. Switching databases
does not automatically copy SQLite data; back up and migrate explicitly.

## Documentation

- [Build status / acceptance](docs/BUILD_STATUS.md)
- [Architecture and storage](docs/ARCHITECTURE.md)
- [AI providers, budgets and cache](docs/AI_ARCHITECTURE.md)
- [Research, models and backtesting](docs/RESEARCH.md)
- [Algorithm review and primary research sources](docs/ALGORITHM_REVIEW.md)
- [GitHub preparation and secret exclusions](docs/GITHUB_SAFETY.md)
- [Signals and validation status](docs/SIGNAL_CATALOG.md)
- [Document, institutional and options research](docs/EVIDENCE_RESEARCH.md)
- [Risk, execution and security](docs/RISK_AND_SECURITY.md)
- [Remaining setup / credentials](docs/USER_SETUP.md)
- [Provider documentation references](docs/PROVIDER_IMPLEMENTATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Original API setup](docs/API_SETUP.md), [Phase 0 readiness](docs/PRE_BUILD_READINESS.md)
