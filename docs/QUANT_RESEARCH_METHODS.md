# TraderX quantitative research methodology

October 15, 2026. This describes implemented research, its evidence boundaries and negative results. It does not claim profitability. Exact measured tables and the accepted run identity are in [the phase report](ALPHA_RESEARCH_REPORT.md).

## Problem formulation

Given information available at time t, estimate future net return, probability of a positive net return, uncertainty and relative opportunity across eligible instruments. The decision includes cash. Forecast accuracy, portfolio utility and executable performance are separate objectives; lower prediction error does not by itself justify a trade.

The alpha registry represents hypotheses, not parameter searches. Twelve identities cover momentum, moving-average trend, breakout, relative strength, cross-sectional ranking, reversal, pairs, volatility, macro/regime, insider events, funding and nonlinear sequence forecasting. These share six conservative dependence groups. Hyperparameter and architecture variants cannot multiply independent votes. Unsupported or unintegrated hypotheses remain IDEA.

## Point-in-time data and identity

The existing configurable universe and versioned historical archives remain authoritative. Availability timestamps, completed sessions, eligibility and source versions are carried into features. The alpha phase uses the previously collected equity/ETF panel and delayed observed-open target artifact. A research plan with code, input hashes, features, dates, constraints, seed and costs is recorded before results. Fixed and Kalman pair relationships are fitted before 2022; sequential updates affect subsequent predictions only. HMM filtering is forward-only, without future-state smoothing. Covariance uses at least 60 common observations strictly before the decision, at most 252; missing returns are not zero-filled.

Current universe survivorship, incomplete delisted coverage, adjusted historical prices and unverified historical liquidity remain limitations. Current sector tags cannot establish historical sector neutrality. Historical market capitalization/shares and valuation vintages are missing; liquidity is not relabeled as size, nor price ratios as value.

## Alpha construction and targets

Cross-sectional research ranks instruments observed at the same timestamp; time-series models condition a given instrument's future on its own prior observations. Six transparent rank references are evaluated at 1, 2, 5, 10 and 20 sessions. Historical entries are delayed to open[t+2], with exit open[t+2+h], and explicit cost assumptions. These are price scenarios, not verified executable fills.

The runtime consumes each registered fitted horizon; a retrospective decay plot never silently changes that target. Current production adapters supply five-session forecasts. Intraday models and automatic optimized holding-period selection are deliberately not claimed. Separately timed prospective quote markouts are a new experiment, not an exact recreation of historical open-to-open targets.

An 18,000-row bounded pre-2022 sample trains standardized Ridge and penalized logistic baselines for the allocation comparison. Six rank references also undergo same-date residualization against prior beta and observable momentum, volatility and liquidity ranks. Descriptive regressions of active returns on SPY and a same-universe momentum spread expose conventional factor dependence. Same-date ranking and residualization require a sufficiently broad cross-section.

## Validation and multiple testing

2022–2024 had already been inspected in earlier research. It is development evidence, even when fitting precedes prediction chronologically. No result from this phase is called a fresh untouched holdout. Reference return streams use nonoverlapping holding windows and date clusters; hundreds of assets on one date are not hundreds of independent experiments. Circular block bootstrap intervals and 1,000 resamples describe dependent return uncertainty. Horizon diagnostics reserve 100 tests for Benjamini–Yekutieli adjustment; missing or withheld comparisons do not reduce that declared count. Pair eligibility uses training-only multiplicity-adjusted cointegration, not later returns.

Prospective promotion uses a single decision per phase at the first 60 nonoverlapping completed decision-date clusters. Gates require a positive net-return lower bound, p < 0.05/(12 × 3), Brier score ≤ 0.25 and maximum drawdown ≤ 10%. A failed gate stays failed for that immutable phase; polling cannot retry until significance appears. A new version starts new evidence and retains the prior failed record. These are operational conservative gates, not a mathematical guarantee of future performance or a familywise guarantee across unlimited future versions.

Historical factor/regime comparisons, bootstrap assumptions and limited sample sizes still require expert interpretation. Raw hypothesis counts and code versions are retained, including failures.

## Portfolio construction and deterministic risk

Seven proposals are compared: equal, edge, inverse volatility, volatility-targeted inverse volatility, risk parity, confidence and constrained mean variance. The risk-parity proposal iterates risk contributions before constraints; after caps it need not have equal risk contributions. Confidence is bounded. Volatility targeting scales the initial proposal before shared hard constraints. Ledoit–Wolf estimates covariance. SLSQP projects proposals into the feasible region; mean variance uses a fixed quadratic risk penalty and turnover-cost penalty. This is a bounded research implementation, not a global-optimality claim.

All methods obey asset 10%, sector 30%, class 60%, gross 80%, correlated-component 25%, ADV participation 0.01%, turnover 40%, annualized volatility 10% and cost 0.3% limits. Correlation components are transitive at |rho| ≥ 0.70. Unknown sector exposures share one conservative group. Fresh historical sleeves budget both entry and exit. Runtime turnover additionally deducts actual fills and pending reservations. The production shadow allocator is entry-only: it cannot spend cash or risk headroom from a position it has merely proposed selling. Required reductions and infeasible optimization block additions; separate exit policies handle existing risk.

The fixed mean-variance shadow configuration is preregistered, not selected because it won this historical comparison. A largely cash result is not evidence of predictive alpha. Downstream risk may further reduce an allocation; an ML prediction cannot bypass caps.

## Costs, execution and attribution

Historical cross-sectional costs come from the frozen source panel. Pair scenarios include 20 basis points round trip per leg and 3% annualized short-borrow cost, without claiming borrow availability or synchronized two-leg fills. Volatility and regime sizing use delayed observed opens with 10 basis points one-way turnover costs. Their prices, spread, market impact and borrow assumptions are not execution guarantees.

Prospective cohorts require fresh, valid bid/ask quotes, session eligibility, a five-second minimum delay and displayed size. Entry uses ask plus slippage and fee; exit uses bid less slippage and fee. An entry expires after one hour without a valid quote. Inadequate exit depth waits instead of fabricating a fill; absent quotes may leave an observation unresolved. Cohorts are bounded hypothetical $100 markouts, not capital-sharing accounts. The existing shadow simulator separately supports partial fills, cash accounting, deterministic sizing, delayed exits and observed-quote excursions.

Shadow entry evidence freezes exact features, model/alpha identities, forecast, uncertainty, regime, allocation plan and exit rule. Completion records actual observed quotes, net P&L, fees and excursions. Entry-weight attribution reconciles each dimension separately to net P&L: alpha, family, asset, regime, sector and sizing plan. Dimensions must not be added together. Attribution is descriptive, not causal; embedded spread/slippage must not be charged twice.

## Forward adaptation and governance

Symbol hashing freezes two lanes: even hashes reserve evaluation; odd hashes permit allocation development only after completion plus seven days. Neither lane enters model training in this implementation. Both may share market regimes, so symbol separation is not statistical independence. Manual and scientific accounts are never repurposed. Original evidence is immutable.

At least 60 independent dates for every eligible family are needed before adaptation. Equal priors are used because no genuinely validated long-run winner exists. Recent 60-window skill is shrunk by n/(n+240), bounded, and blended with at least 80% prior influence. With unchanged eligible membership, each new evidence epoch changes a coordinate by at most two percentage points. Repeated polls are idempotent. Suspension removes unsafe membership immediately, so normalization across a changed membership is explicitly outside that ordinary update bound.

The benchmark compares precommitted equal-hypothesis and adaptive quote-markout sleeves on reserved symbols. It does not yet provide independent complete-account fixed-versus-adaptive performance; the hypotheses can be correlated. No benchmark winner is automatically deployed. Exact-model prospective correlations need at least 40 aligned, nonoverlapping, mature adaptation dates, and matching five-session horizons. Until then the ensemble retains conservative dependence groups.

IDEA → HISTORICAL_RESEARCH → HOLDOUT → FORWARD_TESTING → SHADOW → QUALIFIED_SIMULATION uses immutable definitions and phase-specific evidence. Version changes retire old definitions without deleting them. Required-data failures, extreme feature deviations, deteriorating IC/calibration/net returns, cost inflation and regime failure can suspend new allocations. Three new healthy feature epochs are required to reactivate. Suspended hypotheses may collect observational recovery evidence while remaining blocked from allocation. Governance older than five minutes blocks votes, and restart requires a fresh review. Separate model qualification remains mandatory for the qualified portfolio; an experimental alpha state cannot bypass it.

## What the measured results establish

All 30 reference Rank IC tests fail multiplicity-adjusted significance; average cost-adjusted active returns are negative at all measured horizons. Momentum and relative strength correlate about 0.999. Market and momentum proxies explain about 66% of their active-return variation. The eligible GLD/IAU pair loses after scenario costs. EWMA slightly improves variance loss over realized variance, but not sizing return; GARCH/HMM do not establish a benefit. Original CNN/GRU/transformer folds remain intact, without consistent superiority to Ridge and zero. The constrained optimizer's small positive scenario is overwhelmingly cash and statistically inconclusive.

The credible deliverable is an auditable experimental system, conservative abstention and preserved negative evidence. Independent forward records, reliable historical eligibility and execution-quality data are the next scarce inputs, not a larger neural network.
