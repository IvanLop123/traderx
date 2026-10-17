# Model lifecycle and prospective evaluation

Training creates a portable version with immutable coefficients, input feature names,
training-only scaling/imputation, dataset hash, chronological split and calibration
metrics. A new version is research-only and does not immediately generate a candidate.
Historical gates compare return error with zero and probability error with a training
prior; the holdout needs at least 200 observations and valid calibration.

In Models, choose **Start shadow study** for a stored version. Only future completed
bars after enrollment can start a forward observation. The worker records the exact
model/version, base price/time, prediction and decision time. It waits for the entire
forecast horizon to mature before starting the next observation, preventing overlapping
labels from being counted as separate forward samples. Existing backtests never become
prospective evidence. Outcome records preserve the first evaluated realization.

**Promote for paper candidates** becomes available only when the version passes its
historical gates and has at least 30 nonoverlapping prospective outcomes, lower return
MSE than a zero-return forecast, and lower direction Brier loss than a coin flip.
A new version needs its own study. Only one version per asset is actively studied;
starting another retires the previous one. Retiring preserves all history.

Promotion requires an explicit action. It enables an **Evaluate candidate** action,
which may still return NO_TRADE because expected edge does not cover costs and
uncertainty. Fresh completed history and fresh execution quotes remain necessary.
Any candidate must pass deterministic risk and explicit paper execution. Neither the
worker nor a model invokes a broker. When current forward gates stop passing, the
version becomes ineligible and is returned to shadow status by monitoring. A monitoring
failure also removes paper-candidate status rather than silently trusting it.

Prospective model error is not strategy P&L, a guarantee of profitability, or proof
that outcomes are statistically independent. Thirty forecasts can take substantially
more than thirty days for multi-bar horizons. No forward history was fabricated during
the build; initial versions correctly have zero prospective outcomes. Credentials do
not bypass these controls. Backtests and the internal accounting engine remain usable.

## Scheduled retraining

`GET/PUT /api/v1/settings/training` configures the opt-in local schedule.
`POST /api/v1/models/check-training` checks it immediately. A dedicated hourly
worker performs the same operation in a background thread, independently of
market polling and text inference. Defaults: disabled, BTC/ETH/SOL daily bars,
seven days between attempts, seven new bars, five-bar prediction horizon.

A database lease excludes simultaneous training cycles across processes.
Each asset/horizon tracks its last attempted date and data boundary. A successful
fit creates an immutable research model with input hash, schedule and diagnostics.
Only data already observed and available is admitted; stale/incomplete data is
reported without halting ingestion. The worker never creates a candidate, starts
or retires a shadow study, or promotes an artifact. In-flight fits finish when
the schedule is disabled; the next asset is skipped. Repeated rolling holdouts
are exploratory and do not replace independent forward validation.

The September 29 local smoke test saved a new BTC version using real downloaded
history. Historical gates did not pass; the version remained research-only.
The schedule was restored to disabled after the check.
