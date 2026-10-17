# Troubleshooting

**Dashboard cannot connect:** keep `TraderX.command` open and inspect `data/backend.log`
and `data/frontend.log`. The backend must answer http://localhost:8000/api/v1/health.
A process already using port 3000/8000 is left alone; stop the conflicting process
or configure it deliberately. Do not expose these ports beyond loopback.

**A module has no data:** check System Health. Missing credentials and provider
entitlements are expected empty states. Refresh public data; configured optional providers have independent read schedules and explicit
read controls. Restart after adding credentials. Never replace missing inputs with fixture values.

**Local AI unavailable:** start the local model server, load a model and copy its
exact ID. Save Settings before checking the connection. The endpoint must use
localhost/127.0.0.1/::1 (or host.docker.internal in Docker). Supported local servers
must accept JSON-object chat responses. Off mode performs no health request. A failed local connection can be retried
explicitly after the server is running; failed attempts remain in the usage audit.

**OpenAI paused:** inspect daily/monthly cost, hourly calls and reservations in
Settings. Budgets use UTC calendar periods; failed requests with uncertain outcomes
retain their bound. Do not repeatedly retry an uncertain request. Unknown model
prices require a deliberate entry in config/llm_prices.json. Local/deterministic
work continues independently. Changing provider settings does not cancel already
submitted requests.

**Saved settings differ from .env:** AI settings saved in the UI persist in the
active database while the environment is unchanged. A change to the non-secret
AI environment settings resets the UI override at the next restart. Keys alone
do not enable cloud AI. Credentials come from .env/process environment.

**No candidates:** NO_TRADE is expected when net edge does not clear uncertainty.
A candidate is only research evidence and must pass current risk before any paper
fill. A global kill switch, stale feed or concentration limit will reject it.

**No fills in a strict historical run:** newly downloaded data was not available
in the past. Strict first-observed replay correctly refuses to use it. Retrospective
mode is available but cannot certify revision safety or survivorship correctness.

**Frontend install cache permissions:** use `npm ci --prefix frontend --cache
data/npm-cache`; no administrator permission or change to the shared npm cache is
needed. The app pins a patched PostCSS override and currently passes npm audit.

**Database setup:** run `.venv/bin/python -m alembic upgrade head`. All migrations
were tested on SQLite and a separate PostgreSQL acceptance database. Back up the
whole SQLite database with the database backup API/while stopped, or pg_dump for
PostgreSQL; include the LLM ledger/cache to preserve budgets and deduplication.
Never delete the database merely to reset an AI budget. Do not copy only a live
SQLite .db file while ignoring its WAL.

**Redis unavailable:** market and research continue using the durable database.
The local source-built core Redis lives in ignored data/redis-stable/src; it does
not include Redis Search/JSON modules, which TraderX does not need. The launcher
uses it when present. Docker Compose provides a reproducible Redis alternative.
On this Mac Redis needs LC_ALL=C and --locale-collate C; the launcher supplies them.
