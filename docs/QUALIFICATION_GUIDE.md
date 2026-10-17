# Qualification and Forward Evidence

Open `TraderX.command` in the Desktop `traderx` folder, keep its terminal window open, and visit http://localhost:3000. Keep the computer awake and connected while collecting observations. Closing the launcher stops its services; saved history survives restart. This is local research and simulated trading, not brokerage execution.

From **Portfolio**:

- **Decision diagnostics** explains the original 3,514 decisions and lets you switch to all current decisions. Conditions overlap. An unrequested quote or an unreached portfolio check is unknown, not a passed test.
- **Forward Evidence** lists the 27 registered family/class representatives. Choose **Evidence** for frozen gates, remaining samples, calibration, uncertainty and seven comparison books. Expand **By regime** for conditional portfolio metrics.
- Lower on **Forward Evidence**, inspect the baseline/outlier-clipped family comparisons, conditional regime/liquidity evidence, cross-sectional ranking and meta-label experiments.
- **Replay saved history** runs a disposable historical book using recorded snapshots and actual quotes. It cannot change your manual account, Model Paper account or scientific studies. Missing prices remain missing. Replay never qualifies a model.
- **Scientific studies** retains the original cohorts plus the 80 newly enrolled sentinels. These books are distinct from both personal trading and automatic Model Paper allocation.

## What happens automatically

While running, existing ingestion and scientific workers continue. The qualification collector rotates through up to 12 read-only quote requests per cycle, prioritizes pending orders and candidate holdings, and uses separate candidate, cash, buy-and-hold, momentum, reversion, equal-weight and incumbent books for each asset class. The cycle includes provider latency and then a 30-second pause; it is not a guaranteed 30-second quote feed. Evaluations refresh hourly; collector health is read live in the UI.

Ordinary features, predictions, scores, risk, cost accounting and qualification are local Python calculations. This work makes no LLM calls. A new definition does not import earlier outcomes into its prospective window. After eligible new features and subsequent prices arrive, completed observations accumulate naturally. No number of restarts or API keys can substitute for independent elapsed observations.

A strategy progresses through `RESEARCH_ONLY`, `FORWARD_TESTING`, `INSUFFICIENT_EVIDENCE`, and a fixed terminal `FAILED` or `QUALIFIED_FOR_MODEL_PAPER` decision. Qualification permits only Model Paper consideration; quote checks, current data health, score/probability screens and portfolio limits still apply. Qualifying one family alone does not satisfy the portfolio's two-dependence-group requirement.

Changed model artifacts, criteria or implementation require a new registration. Old registrations and results remain in the audit trail. Missing/stale features, large distribution shifts, unreliable quotes, recent return/calibration degradation or stale approval reviews block new entries; protective exits and accounting continue. Tiny samples are reported as insufficient rather than as proof of drift or quality.

## Training quarantine

No automatic recycling is enabled. To release a cohort later, resolve its pending positions, retire all its source scientific studies, wait until every completed source outcome is at least 90 days old, and make an explicit release with a reason and the required confirmation. The local `/api/v1/qualification/release` endpoint checks these conditions. Release creates immutable source receipts, revokes that cohort's evaluation eligibility and paper authorization, and does **not** automatically train a model. Existing training-release workflows can consume released sources only through their controlled future-training path. A fresh untouched evaluation cohort is required afterward.

## What you need to do now

No new keys or payment are needed for this phase. Keep the app running and inspect **System → Provider health** and **Forward Evidence**. Current strategies have not qualified; holding cash is expected. The current historical development comparisons also did not pass all gates, so meaningful new model research will be needed in addition to elapsed observation time. Do not reduce gates just to generate trades.
