# TraderX v1 architecture

Read-only provider adapters normalize source timestamps and provenance into append-only records and historical parquet archives. Configurable universe eligibility applies price, volume, liquidity, spread and data-quality checks. Known historical-membership and delisting gaps remain explicit.

Deterministic features feed independently evaluated strategy families. Family/dependence grouping, the canonical ensemble, uncertainty, estimated costs, liquidity and portfolio risk produce the TraderX View. Legacy individual models remain readable research experiments, without a normal recommendation UI.

Manual paper trading, Experimental Shadow, qualified Model Paper and scientific forward studies have separate accounts and evidence policies. Previews capture exact evidence. Later fresh quotes determine delayed partial or unavailable fills. Positions, P&L, costs and observed excursions remain reproducible. Forward evidence stays quarantined until an explicit aged release.

FastAPI serves bounded research/control APIs; Next.js renders the eight primary pages. SQLite/PostgreSQL share transactional storage and Alembic migrations. Composite indexes support recent records by kind and symbol. Large model artifacts and datasets stay outside Git. Optional Redis failure uses durable DB jobs.

Optional document extraction runs through the budgeted LLM interface; quantitative services do not depend on it. Provider failures and cost exhaustion do not halt deterministic work. External live-money execution is absent. The separately gated Alpaca paper adapter cannot address a live endpoint.
