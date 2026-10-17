# TraderX — Multi-asset quantitative research and trading platform

TraderX v1.0 is a local quantitative research platform for US equities, ETFs and crypto, with sourced options snapshot analytics and realistic paper execution. Its 502-instrument research universe, independent strategy families, cost-aware ensemble and prospective evaluation ledgers make each decision inspectable. **Real-money trading is not supported.**

## Governed Autonomous Alpha Research Engine

A constrained research director turns new observations into preregistered hypotheses, bounded chronological experiments and recorded rejections or challengers. It works with deterministic templates; optional local/cloud language models propose narrative hypotheses only. Production recommendations and risk controls are never rewritten by the researcher.

**Observe → Hypothesize → Preregister → Experiment → Reject / Challenger → Forward Validate → Qualify**

Research → Autonomous Research exposes lineage, novelty, multiple-testing accounting, compute/storage budgets and pause controls. Defaults are paused and cloud-off. Successful backtests cannot promote themselves: independent forward/benchmark qualification and explicit reviewed model registration remain required. The automatic interpreter starts with bounded Ridge/logistic models; richer model/feature implementations require review. [Architecture, schema, limits and use](docs/AUTONOMOUS_RESEARCH.md).

## Research with explicit limits

- Point-in-time feature availability, publication/vintage checks and frozen model/data identities.
- Configurable liquidity, volume, price, spread and data-quality eligibility. Retrospective universe membership and incomplete delisting returns remain disclosed limitations.
- Cross-sectional relative-return and ranking models alongside classical linear/tree models; bounded CNN/TCN, GRU and transformer challengers remain research experiments.
- Chronological splits, purged holding windows, walk-forward evaluation, calibration, benchmarks, multiple-testing controls and transaction-cost sensitivity.
- Independent family grouping → ensemble → uncertainty → costs/liquidity → portfolio risk → BUY / SELL / HOLD / NO TRADE / INSUFFICIENT EVIDENCE.
- Separate manual paper, Experimental Shadow, scientific forward-study and qualified Model Paper ledgers. Staying in cash is valid.
- Fresh bid/ask checks, delayed execution, spread, slippage, fees, depth participation, partial/no fills and exchange sessions. A historical close is never an executable quote.
- Immutable research provenance and forward evidence quarantined from training; aged observations require explicit controlled release.

**Negative findings are part of the product.** Bounded deep challengers did not consistently outperform simpler baselines. The tested relative-return strategies did not establish independent after-cost alpha. No current model is qualified for automatic Model Paper allocation. Credentials and more runtime do not guarantee eventual qualification or profitability. See [research findings](docs/ALPHA_RESEARCH_REPORT.md), [ensemble comparisons](docs/ENSEMBLE_RESEARCH_REPORT.md) and [methods](docs/QUANT_RESEARCH_METHODS.md).

## Run the existing desktop installation

Double-click `TraderX.command`, keep its Terminal window open, then visit [localhost:3000](http://localhost:3000). Ctrl-C stops the services started by that launcher. Existing credentials stay in your local `.env`; do not replace it with the template.

## Fresh installation

Use Python 3.12 and a current Node.js LTS with npm. From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
npm ci --prefix frontend
cp .env.example .env
mkdir -p secrets data
chmod 700 secrets
chmod 600 .env
.venv/bin/python scripts/dev.py --production
```

The lock contains the core application and statistical research dependencies. The optional bounded neural lab additionally requires `pip install -r requirements-research.txt`; ordinary startup does not import PyTorch. Optional Redis failure falls back to durable database jobs. SQLite is the default; PostgreSQL is supported and migration-tested.

Without credentials the application starts, but it cannot invent market history or provider entitlements. Public crypto data can be collected while configured equity/research feeds remain unavailable. Fill only the providers you intend to use in `.env`, then restart. See [START_HERE](START_HERE.md).

## Daily workflow

Overview → Scanner → asset → TraderX View → Paper Trade → preview → **PLACE PAPER ORDER** → Portfolio → add, trim or exit → Orders / trade history. Notes are optional; evidence is captured automatically. Quotes and displayed depth may prevent fills. There is no Live Trade button.

Primary pages: Overview, Scanner, Assets, Portfolio, Models, Research, System and Settings. Advanced diagnostics stay under Research. System shows provider and worker health; Settings controls the paper account and optional text extraction.

## Optional text extraction

Local, OpenAI, hybrid and off modes share one provider interface. The default is off. No model receives price ticks, indicators, risk calculations or portfolio accounting. Relevant unstructured documents are filtered, cached by content/prompt/model identity and batched where appropriate. Cloud extraction has persistent usage accounting and conservative dollar/rate limits. Budget exhaustion pauses extraction only. No subscription sign-in or conversational product is included in v1.

## Reproducibility and verification

```sh
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m pytest -q
npm run build --prefix frontend
# With the app running:
npm test --prefix frontend
.venv/bin/python -B scripts/api_setup/check_repository.py --history
```

Research runners live in `scripts/research/`. They use authorized local history and save immutable artifacts outside Git; large model runs are explicit, never startup work. See [architecture](docs/ARCHITECTURE.md), [validation and paper assumptions](docs/UNIVERSE_AND_FORWARD_STUDIES.md), and [v1 audit](docs/V1_FINAL_REPORT.md).

## Repository safety

Git contains source, lightweight documentation, templates and configuration only. Credentials, `.env`, private keys, datasets, databases, accounts, logs, model binaries, checkpoints, caches and installed dependencies are ignored. Local hooks run the credential audit before commits/pushes. Do not publish provider data or assume API access grants redistribution rights.

## Future work

Futures, a chatbot, richer options history and additional alternative datasets are postponed. They are not supported v1 product features.

### News evidence

Continuous Alpaca news collection uses existing account access, with deterministic relevance filtering, deduplication, event classification and immediate affected-asset recommendation refresh. News has no validated predictive weight yet; it is forward-collected evidence with a conservative adverse-event entry guard. [Access, latency and limitations](docs/NEWS_INTELLIGENCE.md) are explicit in System. No chatbot or LLM request is involved.
