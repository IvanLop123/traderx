# TraderX ensemble and advanced research completion report

## Decision engine

Final recommendations use one deterministic ensemble contract: BUY, SELL, HOLD, NO TRADE or INSUFFICIENT EVIDENCE. SELL means reducing an existing long holding; it never authorizes a short sale. Each family supplies direction, net edge, probability, uncertainty, applicability, historical/forward reliability and a compatible five-session horizon.

Implemented family adapters: momentum, trend following, breakout, relative strength, cross-sectional ranking, mean reversion, statistical relative value, volatility, insider/event, macro/regime and crypto funding. The advanced-ML adapter is present but abstains: research challengers have not been deployed or qualified. Coverage differs by asset and timestamp; an implemented adapter is not evidence that its inputs are currently available.

| Family | Assets with a usable current forecast |
|---|---:|
| breakout | 479 |
| cross_sectional_ranking | 471 |
| mean_reversion | 501 |
| momentum | 498 |
| pairs_relative_value | 16 |
| relative_strength | 487 |
| trend_following | 462 |
| volatility | 485 |

Current actions: {'NO TRADE': 498, 'INSUFFICIENT EVIDENCE': 4}.

Variants are deduplicated before representative selection. Related trend/ranking/advanced-price models share the price-trend group; mean-reversion/pairs share price-reversion. Other groups are price-volatility, macro, insider and funding. Two distinct supporting groups are required; any group has at most 50% of total weight. Group names are conservative dependence controls, not proof of statistical independence. There is no single-family entry exception.

Weights compare equal, fixed historical and dynamic evidence-discounted modes. Historical skill is shrunk toward a neutral prior (minimum 40 independent dates, 120 prior dates). Conditional/forward discounts require at least 30 dates and shrink toward the prior. Recent gains cannot grant a weight bonus. Available regimes/liquidity contexts may discount weights; class-specific models provide class context. Dated sector/industry and adequate volatility-conditional calibration are not available, so no fabricated estimates are used. The bounded historical dynamic experiment had insufficient conditional dates and correctly fell back to fixed weights; it did not demonstrate an advantage.

Ensemble uncertainty combines residual scale and disagreement without assuming independent errors. Positive expected edge can remain NO TRADE. Existing qualification and hard risk checks remain additional gates for Qualified Model Paper. Fresh quotes replace estimated research costs before fills.

## Four separate paper environments

Manual Paper, Scientific Forward Studies, Qualified Model Paper and Experimental Shadow have separate ledgers. The shadow worker runs automatically while TraderX is open, prominently labeled **EXPERIMENTAL — NOT VALIDATED**. It reuses local delayed bid/ask execution, fee/slippage/depth/partial-fill/session controls and deterministic position, cash, concentration, liquidity and drawdown limits. No broker adapter is reachable from it.

Entry decisions retain the exact forecasts/features, available-at timestamps, model references, ensemble version/weights, risk sizing, quote and intended exit rule. Fills and completed immutable outcomes retain fees, P&L, observed favorable/adverse excursions, regime and entry-weight family attribution. Attribution is an allocation of P&L, not causal alpha attribution. Cash decisions are recorded once per evidence identity. Manual notes remain optional and are never training inputs.

Production shadow: 0 orders, 0 completed trades, 0 positions, $0.00 realized simulated P&L at acceptance. Cash is the correct outcome under the current gates.

Disposable offline browser acceptance: four entries, delayed fills, 100 duplicated momentum variants without extra influence, changed evidence, four automatic exits, $66.23 fictional net P&L and family attribution. A separate manual trade remained open with Follow TraderX exits OFF, then exited only after explicit consent. These fictional quotes/results never entered production or scientific evidence.

## Exits

Automatic shadow exits cover reversal, edge loss, deterioration, fixed horizon, volatility stop and protective loss/drawdown limits. Research also compares trailing and profit-taking rules. Manual per-position Follow TraderX exits defaults OFF; consent binds to account, symbol and position opening time. Reopening does not inherit consent. Chosen rules use a five-session horizon, 5% protective loss limit, 2× daily-volatility stop, 5% trailing threshold or 10% profit threshold. Stops request subsequent simulated execution and do not promise their trigger price.

The historical eight-rule comparison generated zero qualifying entries in all three folds. Therefore there is no empirical winning exit rule from this run. Programmatic and browser tests exercise the exit lifecycle; they are not trading-performance evidence.

## Advanced quantitative results

Three chronological folds (2022, 2023, 2024), 490–492 US equities/ETFs and 18,582 / 18,690 / 18,784 identical test rows per model. Training, earlier stacking/weight calibration and later probability/interval calibration precede testing. Outcomes are purged and separated with a seven-day embargo and nonoverlapping date clusters. These historical periods were inspected in prior phases: they are chronological out-of-sample diagnostics, **not untouched prospective holdouts**.

The local CPU experiments train a small temporal CNN, GRU and transformer for five fixed epochs on 12-observation windows (up to 18,000 training rows). No architecture or epoch is selected using test loss. Baselines/challengers include zero, historical mean, regularized momentum/reversion, pooled ridge, PCA/ridge, random forest, histogram gradient boosting, meta-labeling, stacking and equal/fixed/dynamic ensembles. XGBoost/LightGBM are explicitly unavailable; no dependency or result was fabricated.

| Model | 2022 MSE | 2023 MSE | 2024 MSE |
|---|---:|---:|---:|
| zero | 0.004286 | 0.002658 | 0.002924 |
| historical_mean | 0.004217 | 0.002662 | 0.002918 |
| momentum | 0.004216 | 0.002666 | 0.002920 |
| ridge | 0.004246 | 0.002686 | 0.002923 |
| random_forest | 0.004316 | 0.002710 | 0.002924 |
| gradient_boosting | 0.004500 | 0.002711 | 0.002924 |
| pca_ridge | 0.004228 | 0.002670 | 0.002920 |
| stacking | 0.004208 | 0.002683 | 0.002940 |
| meta_label | 0.004287 | 0.002671 | 0.002924 |
| ensemble_equal | 0.004220 | 0.002663 | 0.002918 |
| ensemble_fixed | 0.004220 | 0.002663 | 0.002918 |
| ensemble_dynamic | 0.004220 | 0.002663 | 0.002918 |
| tcn | 0.004285 | 0.002667 | 0.002934 |
| gru | 0.004235 | 0.002671 | 0.002923 |
| transformer | 0.004280 | 0.002681 | 0.002924 |

2024 ridge rank IC was +0.036 versus transformer +0.008, GRU +0.009 and CNN −0.009. All reported model rank-IC adjusted q-values were 1.0. No reliable alpha superiority was demonstrated. Constant forecasts have undefined ranking/decile metrics; the report explicitly corrects earlier arbitrary tie-break diagnostics without altering fitted predictions. Original artifacts are retained.

Diagnostics include date-block IC intervals/stability, net top/bottom deciles, turnover, calibration/Brier error, empirical residual-interval coverage, drawdown, cost drag, liquidity/regime buckets, feature weights/importances and model correlations. Factor-neutral comparisons remove contemporaneous momentum/volatility/liquidity-rank exposure. Historical sector/cap metadata is missing, so sector-neutral and cap-stratified claims remain unavailable.

Statistical experiments fit PCA factors, predefined-pair Engle–Granger cointegration tests and one-step Kalman relationships. Pair results are descriptive: no validated borrow/two-leg fill archive exists. EWMA, GARCH(1,1) and a two-state HMM were tested on the next observed squared SPY daily return. EWMA had lower variance MSE than GARCH in all three years; HMM did not consistently improve it. HMM inference uses forward filtering, not future-aware backward smoothing.

Portfolio research compares equal weight, volatility targeting, inverse volatility, capped positive edge, approximate risk parity and covariance-constrained minimum variance with Ledoit–Wolf shrinkage. All retain cash, prohibit leverage/shorts, cap positions at 10%, gross exposure at 80% and estimated ADV participation. They use nonoverlapping daily-open return diagnostics with conservative costs, not claims of historical executable fills. Missing covariance observations and historical universe membership remain limitations.

Circular date-block bootstrap and Benjamini–Yekutieli accounting reserve 111 hypotheses including unavailable/failed and portfolio/exit/statistical comparisons. This reduces multiple-testing optimism; it does not repair survivorship bias or make already-inspected history untouched. Residual-quantile intervals report empirical coverage, without claiming exchangeability in financial markets. Filings/ALFRED retain their existing point-in-time pipeline; these bounded price challengers do not invent missing fundamental data.

**Conclusion: no new method has demonstrated genuine, independently validated generalization improvement. No automatic model replacement or promotion occurred.**

## Integrity and acceptance

## Run and use

Double-click `TraderX.command` in `/Users/ivanlopez/Desktop/traderx`, keep its terminal open and visit http://localhost:3000. The app is already running at handoff.

Use **Portfolio → Experimental Shadow** for automatic unvalidated local simulation; pause/resume changes entries while protective exits continue. Use **Research → Advanced Research** for comparisons and ensemble weights. Use **Portfolio → My Manual Portfolio** to optionally enable exits separately for a position. Leave Scientific Studies untouched to collect independent evidence.

No new API keys are required for this phase. Existing entitled read-only providers supply data. Optional future improvements need legitimate historical membership/delisting, dated sector/capitalization, higher-quality execution/borrow history and enough elapsed forward observations—not a more expensive LLM. The advanced research job is explicit and bounded (`.venv/bin/python scripts/research/advanced_research.py`); it does not train continuously or run per tick. Optional research dependencies are in `requirements-research.txt`.

## Method references

- [Chronological splits and gap parameters](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
- [PyTorch sequence model primitives](https://docs.pytorch.org/docs/stable/nn)
- [Engle–Granger cointegration test](https://www.statsmodels.org/dev/generated/statsmodels.tsa.stattools.coint.html)
