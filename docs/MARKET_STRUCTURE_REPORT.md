# TraderX market structure completion report

October 14, 2026. This phase is complete for local research and simulated execution. No strategy was promoted and no independently validated profitability improvement was established. The application remains in `/Users/ivanlopez/Desktop/traderx`.



## 1. Why 556,521 and 1,280,806 were both correct

556,521 described the earlier phase's original SQL `records` rows across all record kinds. It was not a count of historical daily price bars. 1,280,806 described primary daily bars in 501 historical parquet archives. SQL evidence, raw responses, manifests and derived panels are different datasets from those price archives.

The read-only audit performed before implementation found 1,280,856 primary bars: 50 equities had each gained one real session since the earlier snapshot. The final acceptance found 1,280,868, including 12 additional crypto bars from ordinary refresh. Raw and adjusted counterparts and superseded vintages are retained but not double-counted as primary history. Five old unreferenced acceptance fixtures contain 1,995 fictional rows and are explicitly excluded from real market coverage.

At the initial audit, the primary count consisted of 941,157 adjusted stock bars, 329,866 adjusted ETF bars and 9,833 raw crypto bars. The full audit enumerates tables, record kinds, provider, frequency, adjustment and active/superseded status, including duplicate representations and SQL bars. No destructive repair was required.

## 2. Preservation

All 556,521 earlier baseline records were found unchanged in the initial audit. The phase-start baseline then contained 571,138 SQL records; final verification found **zero missing and zero changed**. All **1,328 original parquet files** retained their hashes. The prior history manifests and model/ensemble/deep results remain intact.

A private SQLite backup and hash inventory remain under ignored `data/market_structure_phase/`. The manual, experimental ensemble and qualified paper accounts retain the same account identity, cash, realized P&L, fees, positions and orders; valuation marks may update. There were zero new manual orders, fills, resets or consent changes. The final audit counted 608,793 SQL records, 27 current forward-testing definitions, 243 superseded definitions and 141 scientific enrollments. Current implementation fingerprints matched. Superseded definitions remain stored.

## 6. Options features actually available

The configured Alpaca indicative endpoint returned **1,708 AAPL contracts across 13 expirations** in the bounded snapshot. The UI exposes observed strike/IV surface, expiration term structure, available Greeks, expected moves, descriptive skew, quote quality and trailing realized-versus-implied volatility. Optional local European Greeks/IV calculations and cost-aware parity diagnostics are deterministic and tested.

Two saved snapshots are from the same date, so they count as only one history day. Provenance distinguishes provider data from local approximations. Indicative quotes are modified and trades delayed according to the [provider documentation](https://docs.alpaca.markets/us/reference/optionchain); they are not asserted to be executable.

## 7. Options fields still unavailable

Synchronized executable underlying/option quotes and costs are missing for a live parity claim. American exercise, dividends and borrow complicate European parity approximations. No options-order execution was added.

## 8. Intraday coverage

The first bounded collection stored **24,188 real bars in 12 series**, October 7–14 UTC (end exclusive), from the configured Alpaca SIP historical feed and public Coinbase candles:

| Asset | 1 minute | 5 minute | 15 minute | 1 hour |
|---|---:|---:|---:|---:|
| AAPL | 4,163 | 955 | 320 | 80 |
| SPY | 4,375 | 959 | 320 | 80 |
| BTC-USD | 10,080 | 2,016 | 672 | 168 |

These are archive coverage counts, not a claim that every row passes regular-session feature eligibility. Features include momentum, opening gap, fully observed opening range, time-of-day relative volume, actual source VWAP distance, intraday volatility, high/low location and overnight versus regular-session changes. Missing intervals and crossing-session bars are not filled or relabeled. Equity holidays/DST and crypto UTC 24/7 are separate.

Defaults bound collection to three assets, seven days, four resolutions, once daily, 80 requests per cycle and 250 MB for module records. Storage checks serialize across writers. Existing evidence is not deleted when limits are reached. See [Alpaca bars](https://docs.alpaca.markets/us/reference/stockbars) and [Coinbase candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles) for source behavior.

## 9. Microstructure

Sampled spread, quote age and quote/trade intensity are supported. Genuine optional book data enables depth, imbalance and a displayed-book impact scenario. Current missing depth remains missing; the optional book collector was not silently enabled. Snapshots are labeled forward-collected evidence, not a complete historical order book or queue/impact model.

## 10. Recommendation lifecycle

A separate worker checks 502 assets once per minute and stores initial states and material transitions. Identical polls are suppressed. Changes include action, supporting families, regime, eligibility, health/cost gates, held status and model horizon. Edge/uncertainty thresholds are the greater of 0.25 percentage points or 25% of the prior material value, so smaller cumulative movements can eventually trigger a transition.

Each event retains timestamped prior/new states and evidence. Research and the Daily Decision Board display them. Compatible 1/2/5/10/20-session interfaces are implemented; existing fitted models remain five-session models. Polling faster does not transform a daily model into an intraday model. Different horizons cannot vote in the same ensemble.

## 11. Experimental Shadow Portfolio

Automatic local entries still require multiple independent families, positive estimated edge after costs, acceptable uncertainty, liquidity, fresh prices and deterministic risk approval. Staying in cash is valid. Exits record reversal, edge disappearance, confidence deterioration, risk limits, model horizon or regime incompatibility.

At acceptance the ensemble shadow account had zero orders, positions and portfolio outcomes. Three older statistical shadow outcomes were preserved separately. New portfolio outcomes use a distinct record kind to prevent legacy-record crashes and accidental model-training contamination. No gates were weakened to manufacture trades.

## 12. Manual Follow TraderX exits

The setting defaults OFF. Choices are reversal only, loss of edge, recommended exits and never automatic. The first two use only the selected condition; recommended exits include protective rules and the actual model horizon. Never automatic forces consent off. Disabling cancels pending automatic exits for that consent while preserving separately submitted manual orders. Real subsequent simulated-fill conditions still apply. Entry evidence is automatic and subjective notes remain optional. No production consent was changed during verification.

## 13. Alpha-decay findings

Three declared rank signals—momentum, mean reversion and low volatility—were evaluated at 1, 2, 5, 10 and 20 sessions on already-inspected 2022–2024 stock/ETF history, with delayed next-available opens, nonoverlapping horizons, costs, block-bootstrap uncertainty and 30-test Benjamini–Yekutieli accounting. This is historical diagnostic research, not a new untouched holdout.

| Five-session signal | Rank IC | Mean top-decile net return | Mean active return versus universe |
|---|---:|---:|---:|
| Momentum | −0.0091 | −0.43% | −0.78% |
| Mean reversion | +0.0174 | −0.46% | −0.82% |
| Low volatility | −0.0091 | −0.29% | −0.64% |

All 15 IC adjusted q-values were 1.0. Active returns were negative across all signal/horizon combinations. Lower q-values on some negative active returns indicate underperformance, not profitable alpha. Twenty-session momentum had positive net return but negative relative return. No useful universal holding period or profitable signal was established.

## 14. Capacity findings

Sensitivity scenarios cover $100, $1,000, $10,000, $100,000 and $1,000,000 orders using available volume, base costs and a volatility/participation impact assumption. Larger sizes worsen estimated returns. All capacity classifications remain **INSUFFICIENT EVIDENCE**: calibrated impact, executable historical depth and queue data are missing. No low/moderate/high capacity certification is claimed.

## 15. Statistical and quantitative methods

The earlier bounded cointegration/pairs, Kalman, PCA, Hidden Markov, EWMA/GARCH, cross-sectional, meta-label, covariance-shrinkage, risk-parity, constrained-allocation and volatility-targeting experiments/results remain available in Advanced Research. This phase adds the three distinct fixed rank hypotheses, horizon decay, capacity sensitivity and strategy-return correlations. It does not rerun every earlier strategy or add complexity to obtain a favorable result. Full regression/model tests pass.

## 16. Deep challengers

CNN, GRU and transformer results showing no demonstrated advantage remain unchanged. No larger neural architecture or reinforcement learning was added. The existing local model interfaces and comparison records are preserved.

## 17. Strategy-return correlation

Correlations use 94 aligned, nonoverlapping five-session active-return periods: momentum/mean reversion **0.1613**, momentum/low volatility **−0.4183**, mean reversion/low volatility **−0.6429**. These are realized rank-strategy streams, not correlations between labels or proof of independence among different fitted models.

The ensemble accepts an optional exact-model dependence profile with matching horizon, point-in-time availability and at least 40 nonoverlapping observations. Strong positive correlation can conservatively merge dependence groups; it cannot boost confidence. No proxy-factor profile was applied to current fitted-model recommendations.

## 18. Reproducibility

Completed run: `structure_exp_d692ba7d9e7b38f2ea24a1bfba7ab442863fb9d8c6a3e9ebc7390ed4747c084b`.

Frozen identity includes code hash, dataset snapshot and archive versions, features, universe, dates, targets, hyperparameters, seed 41, package/Python versions and cost assumptions. Feature/target parquet and realized-return artifacts have verified hashes. Identical identities reuse results. The UI compares saved identities and results. A failed first plan remains recorded; the corrected run completed, rather than erasing an unsuccessful attempt. Manual and forward-shadow outcomes were not recycled into this experiment.

## 19. Out-of-sample improvement

**None established.** The added diagnostics improve observability and execution/research correctness, not demonstrated investment returns. No model was promoted. All 27 current definitions remain forward-testing; zero strategies are qualified. Independent observations must accumulate over real time.

## 20. Final verification

## 21. Remaining limitations and required user actions

## 22. Credentials and repository

Existing credentials are unchanged. `.env`, `secrets/`, local databases, archives, models, backups, runtime/build artifacts and research outputs remain excluded by repository rules. The local working tree, index and reachable local Git history passed the repository's heuristic secret audit; this is not a certification of remote repositories or an exhaustive security assessment. No push, publication or distributable archive was made.

## 23. External execution and paid inference