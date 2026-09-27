# Research and model limitations

A saved experiment records its hypothesis, symbol, forward horizon, sample size,
coverage, rank correlation, forward-return distribution and a deterministic block
bootstrap interval. Results append with new IDs. Repeated runs are counted; an FDR
utility exists for multiple p-values. A full experiment-family discovery control
workflow is not yet integrated in the UI.

The current backtester is a single-asset, long/cash daily momentum simulator.
The decision uses a completed earlier bar and executes at a later open. Costs
include configurable fees, half-spread and slippage. End-of-run liquidation is
charged. Equity, benchmark, drawdown, Sharpe, Sortino, turnover and fills are stored.
A strict observed-time option forbids history downloaded today from trading in the
past. The default retrospective mode permits completed historical bars but explicitly
warns about provider revisions. Neither mode resolves survivorship bias without an
appropriate historical universe dataset. No profitability claim is made.

The baseline learns expected return with ridge regression, direction with logistic
regression and squared-return volatility with ridge. Standardization fits training
only. A fixed 60/20/20 chronological split purges the forward horizon at boundaries;
validation trains sigmoid calibration; holdout evaluates the fixed model once per
run. Repeated runs on the same holdout invalidate independence claims. Future prices
are never used in the historical feature calculations.

The registry persists training/split times, feature names, hyperparameters, dataset
hash, validation/holdout metrics, calibration, uncertainty and JSON model coefficients.
Registered inference can run without retraining or unsafe pickle loading. Optional
numeric evidence is joined as-of actual availability and selected only with sufficient
training-period coverage. Missing sources are listed as insufficient coverage, not
filled with invented financial signals. Training-period medians are saved when needed.

Contributions are the standardized input multiplied by each return coefficient,
including negative/conflicting inputs; they are model arithmetic, not LLM rationales.
Prediction → candidate requires estimated edge after costs to exceed the uncertainty
bound and a configured positive-return probability. NO_TRADE is a normal outcome.
All research models remain research-only and cannot automatically execute.

Not implemented as a finished system: multi-asset portfolio/event backtesting,
options exercise/assignment, prediction-market settlement, historical order-book
partial fills, verified wallet visibility/latency replay, full production model-selection governance, portfolio correlation stress tests and production
signal calibration across every requested intelligence family.


The strategy comparison adds fixed cash, buy-and-hold, 20-day momentum,
multi-horizon trend, volatility-targeted trend, and mean-reversion challengers.
Selection uses the development sample only; a trailing 25% holdout reports normal
and increased costs. Three expanding, purged forecast folds remain entirely inside
development data. Trial counts and repeated-holdout warnings are retained. These
are six research baselines, not a profitable strategy search or a replication of
institutional trend-following portfolios. See ALGORITHM_REVIEW.md.

New model records include zero-return MSE and training-prior Brier benchmarks.
Candidate eligibility requires both benchmarks to be beaten, at least 200 holdout
observations and available validation calibration. Edge, uncertainty and risk gates
still apply. This gate is a minimum diagnostic, not permission to deploy a strategy.
Volatility version 2 subtracts squared expected return from predicted second moment;
versioned JSON artifacts preserve version 1 inference semantics.
