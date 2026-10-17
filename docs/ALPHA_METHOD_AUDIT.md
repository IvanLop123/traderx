# Advanced Research audit before this phase — October 14, 2026

This audit distinguishes running numerical implementations, measured experiments, and direct regression coverage. Existing results are retrospective development evidence, not untouched profitability validation. Earlier records will not be rewritten.

| Requested method | Existing implementation and measured use | Test/evidence boundary |
|---|---|---|
| Regularized linear/logistic | Ridge and penalized logistic; strategy fits and calibration; three advanced chronological folds | Existing strategy/model tests and recorded fold metrics |
| Random forest | 60 shallow trees, fixed settings; three advanced folds | Recorded real fits; no dedicated standalone forest regression test |
| Gradient boosting | sklearn histogram gradient boosting; three folds | Recorded real fits; not XGBoost/LightGBM |
| CNN | Small causal dilated Conv1d (TCN) | Bounded training regression test and three saved folds |
| GRU/LSTM | GRU implemented and measured | GRU training test; LSTM absent and not needed as a duplicate hypothesis |
| Transformer time series | One small causal encoder with positional embeddings | Training test and three saved folds; no demonstrated advantage |
| Cross-sectional ranking | Pooled regularized returns with cross-sectional ranks; decile/Rank IC evaluation | Existing strategy tests and real saved results; no dedicated listwise neural ranker |
| Meta-labeling | Logistic gate fitted on earlier calibration segment | Saved fold results; isolated chronology coverage to strengthen |
| PCA/statistical factors | Training-only PCA plus Ridge | Saved folds and loadings; not a fundamental factor model |
| Cointegration/pairs | Five predeclared pairs; training-window cointegration, multiplicity adjustment, later spreads | Measured diagnostic results; executable two-leg P&L absent |
| Kalman relationships | Sequential dynamic hedge coefficients and prediction error | Saved pair results; no future smoothing; dedicated chronology tests to add |
| Hidden Markov regimes | Training fit and forward-only filtering | Saved variance results; regime-based portfolio benefit not evaluated yet |
| EWMA | Sequential variance forecasts | Saved next-day squared-return error; downstream sizing comparison missing |
| GARCH | Fitted GARCH(1,1), sequential forecasts | Saved variance results; downstream sizing comparison missing |
| Factor neutralization | Same-date residualization on momentum/volatility/liquidity ranks | Recorded neutral Rank IC; market beta/sector analysis missing; size/value data absent |
| Covariance shrinkage | Ledoit–Wolf in portfolio comparison | Real fits; prior code zero-fills missing return history, explicitly disqualifying it |
| Volatility targeting | Deterministic target scaler | Allocation cap tests and saved portfolio comparisons |
| Risk parity | Iterative risk-contribution balancing | Allocation cap tests and saved comparisons |
| Constrained optimization | Capped long-only minimum variance | Allocation tests; not full mean-variance with all requested portfolio constraints |

The existing ensemble groups correlated price families and never counts duplicate model variants as independent votes. Its conditional reliability discounts are not a separately governed adaptive-versus-fixed forward experiment. An alpha registry and lifecycle are missing; model qualification alone is not an alpha registry.

The justified additions are alpha identities/governance, separated prospective allocation/evaluation evidence, constrained portfolio construction, beta/proxy-factor diagnostics, executable-price delayed research scenarios for predeclared pairs, sequential regime/volatility sizing comparisons, and dedicated chronology/constraint tests. No larger neural model, LSTM duplicate, new data provider or asset class is justified. Market-cap/value and dated sector-neutral historical claims must remain unavailable without legitimate point-in-time data.
