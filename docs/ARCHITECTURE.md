# Architecture

One FastAPI backend, one Next.js/TypeScript frontend, and one durable database.
SQLite is the convenient native default; PostgreSQL uses the same SQLAlchemy
contracts and Alembic migrations. Redis publishes update notifications when present.
The app remains operational when Redis or every AI provider is unavailable.

Flow: provider reads → raw records → normalized events → local features/signals →
research/model versions → predictions → optional candidates → deterministic risk →
persisted approved orders → explicit internal paper fills → portfolio state.

`backend/schemas/contracts.py` defines assets, raw records, events, evidence,
features, signals, predictions, candidates, assessments, approved/rejected orders,
execution reports, fair probabilities and opportunities. Typed inputs reject NaN,
infinity and unknown fields. Datetimes representing availability are timezone-aware.

`records` is an indexed append-only JSON envelope for different research domains.
Kinds include raw, event, quote, bar, document, feature, signal, theme, model,
prediction, model_inference, candidate, risk_assessment, approved_order, fill, audit,
backtest, experiment, macro, energy, trader and prediction_market. This keeps source
shapes flexible without creating empty tables for unavailable feeds. `settings`
stores safe UI configuration, provider status and transactional paper state;
`llm_runs` stores permanent cached outputs and spend; `jobs` stores durable text
work, leases, attempts, deferrals and dead-letter outcomes.

Events retain occurrence/publication/first observation/ingestion/processing times.
Document and event hashes deduplicate unchanged input. Bar content versions retain
the first observed time. Optional numeric features join by actual availability, not
event date. No future filing or later amendment is retrospectively available to
model input. Retrospective downloaded market bars remain separately labelled.

The market loop defaults to 60 seconds, with hourly historical/context refresh.
Text jobs run independently and never block it. Provider timeouts/backoff/status
are isolated. WebSockets expose periodic market/portfolio snapshots without making
additional provider or LLM requests. This is a polling implementation, not a native
exchange tick/order-book stream. Public history is currently bounded to 290 daily
bars per Coinbase request.

The frontend uses a same-origin API proxy. The backend binds to loopback, restricts
Host/Origin headers and requires a custom header for mutations. Do not expose it
to the Internet without authentication, HTTPS and a separate deployment review.
