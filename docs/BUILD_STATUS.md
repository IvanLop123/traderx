# Build status — September 27, 2026

**TRADERX_MAIN_BUILD_INCOMPLETE**

The delivered application runs locally and supports real market research and an
internal paper simulator. The optional-provider/AI architecture and current review
are implemented. The much broader original main-build specification is not fully
implemented; credentials alone cannot supply missing engineering or validation.
This document distinguishes usable functionality from that remaining scope.

## Delivered and exercised

| Area | Working scope |
|---|---|
| Application | FastAPI API, modular Next.js UI, local launchers, responsive views, evidence drawer, explicit chatbot |
| Storage | Durable raw/event/feature/signal/model/research/portfolio records, SQLAlchemy, Alembic on SQLite and PostgreSQL, optional Redis |
| Market ingestion | Public Coinbase quotes and three years of daily history, Hyperliquid perpetual context and public wallets, Kalshi public demo observations |
| Optional feeds | Alpaca quotes/history, SEC submissions and bounded document ingestion, Alpha Vantage news/transcripts/options, FRED vintage observations, EIA, explicit X reads |
| Scheduling | Independent configured-provider schedules, persisted due times, durable text queue, isolated failures |
| AI | Off/local/OpenAI/hybrid, canonical provider interface, optional local key, filters/batching, permanent successful-result cache, provenance, budgets and persistent usage |
| Numerical research | Technical features/regime, chronological regularized models, calibration, stored coefficients, optional as-of features, simple benchmark gates |
| Backtesting | Cost-aware daily long/cash simulation, fixed strategy comparison, three purged expanding folds, strict observed-time option, warnings and retained trials |
| Evidence research | Form 4 owner/transaction parsing, rolling observed insider clusters, amendment invalidation, 13F holdings/period changes and same-quarter observed-manager consensus, transcript Q&A/period lexical comparisons, provenance and expiry |
| Other intelligence | Historical options liquidity/volume-OI/IV/skew summaries, source-backed themes, wallet/CSV metrics, European Greeks/parity, probability utilities |
| Internal paper | Cash/positions/fees, fresh risk approval, stale/invalid-quote rejection, concentration/loss limits, kill switch, idempotent fills, UI position exits |
| Security | Local-only binding, origin/host checks, credentials kept server-side, Git/Docker exclusions, local commit/push audits, preserved existing secret files |

## Still required for the complete original specification

- External Alpaca paper brokerage order submission, durable reconciliation and
  venue-specific execution adapters. The current executor is **internal paper only**.
- Native exchange streaming/trades/order-book history and multi-asset event-driven
  replay with partial fills, measured impact and a corporate-action/universe policy.
- Options assignment/exercise, funding/borrow and prediction-market settlement
  lifecycle in portfolio backtests/execution.
- Complete historical insider/holdings coverage and amendment reconciliation,
  market-wide institutional crowding, validated transcript prediction models,
  semantic relationship/bottleneck inference and source-family predictive
  calibration. Implemented observed-source comparisons do not establish those claims.
- Full social velocity/coordination research and verified wallet publication-delay
  replay. The current copyability figure is cost sensitivity, not latency evidence.
- Portfolio correlation/sector stress, full PBO/deflated-Sharpe or experiment-family
  governance, validated model promotion/monitoring and independent forward history.
- Public deployment authentication and operational hardening. Do not expose the
  local application directly to the internet.

## Verification and access limits

Verification: **93 backend tests plus 8 subtests**, **12 frontend HTTP checks**,
a successful production build/type check, and a passing repository audit.

The backend suite covers AI isolation/cache/cost gates, provider normalization and
failure isolation, document security, leakage controls, paper accounting/risk and
PostgreSQL transactions. Frontend HTTP tests cover pages, proxy connectivity, origin
isolation, credential-free settings and metadata. Production build/type checks,
dependency checks and repository audits pass. Browser workflows were manually
exercised, including actual strategy comparison on downloaded market history.
The additional populated earnings, insider, institution and options screens were
exercised using a separate, explicitly labeled acceptance database. It is never
used as the production research database. See EVIDENCE_RESEARCH.md for scope and
data-quality rules.

Public provider tests and local GS Quant calculations passed. Optional credentialed
feeds were tested through mocks and missing-key behavior, not authenticated live
access. No local model was installed, so actual LM Studio inference still needs a
loaded compatible model. No paid LLM call or external order was submitted. Docker
Compose is supplied but was not executed because Docker is absent on this Mac;
native PostgreSQL was exercised separately.

The app starts with AI off, automation/escalation off and the paper kill switch on.
These defaults do not inhibit data ingestion or research. See USER_SETUP.md for
remaining account/model setup, ALGORITHM_REVIEW.md for findings, and
GITHUB_SAFETY.md before publication.
