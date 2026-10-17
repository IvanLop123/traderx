# TraderX qualification pipeline — October 12, 2026

The qualification collector and UI are implemented and running locally. **Zero strategies genuinely qualify for Model Paper.** Real/external trading remains disabled. The engineering positive path passes using isolated test data; those fabricated test observations never enter the user's database or scientific results.

## Why the original 3,514 decisions were NO_TRADE

These were seven repeated evaluations of **502 asset/feature snapshots**, not 3,514 independent return tests. Counts overlap:

| Condition | Decisions |
|---|---:|
| No qualified strategy evidence | 3,514 |
| Displayed score below 65 | 3,514 |
| Uncapped research score below 65 | 3,514 |
| Expected edge after estimated costs nonpositive | 3,458 |
| Expected edge unavailable | 7 |
| Available probability below 0.55 | 3,507 |
| Probability unavailable | 7 |
| Invalid/missing uncertainty | 7 |
| Invalid/missing volatility | 7 |
| Asset eligibility unavailable/failed | 112 |
| At least one excluded vote had missing/invalid features | 3,388 |
| At least one excluded vote had drift/extreme features | 3,507 |
| Stale-data flag | 0 |
| Fewer than two research dependence groups | 7 |
| Observed disagreement among groups | 98 |
| Nonpositive net edge but net edge plus cost estimate positive | 3,129 |
| Observed drawdown, position or capacity exhaustion | 0 |
| Quotes not requested | 3,514 |
| Later portfolio-capacity checks not reached | 3,514 |
| Calibration qualification not established | 3,514 |

The feature counts describe **at least one excluded family vote**, not necessarily rejection of the entire asset. Disagreement discounts the score; it is not an extra hard veto. Finite uncertainty reduces score/size rather than facing an invented standalone ceiling. The gross/net edge comparison is a descriptive cost proxy, not proof that removing fees causes profitability. Calibration-drift flags were zero because no adequate calibration sample existed, not because calibration was proved good.

**No candidate passed all other observed screens and was blocked only by qualification.** Removing the qualification score cap and testing 50, 60, 65, 70 and 80 still yields zero passes for these original records. The evidence supports weak expected edge/probability plus missing qualification; it does not establish that the system's score cutoff alone was unnecessarily restrictive. Unreached quote/liquidity and portfolio checks remain unknown.

## Frozen qualification rules and states

Every active definition binds a model artifact hash, implementation hash, criteria hash, frozen risk policy, asset class, universe, liquid scientific sentinels, dependence group and comparator definition before its observations are evaluated.

1. Three chronological historical development folds must each have a positive lower after-cost return bound, better MSE than zero-return prediction, and better Brier loss than the earlier training base rate.
2. The first **40 nonoverlapping prospective completed-date clusters** are a holdout. The next **60** are forward evaluation. Asset outcomes on the same entry date are averaged; overlapping label spans are purged. Repeated snapshots earn no extra independent sample.
3. Both prospective return lower bounds must be positive after costs. Inference uses fixed-seed circular five-observation block resampling, 99,999 draws, and a conservative family/comparison adjustment of 0.05 / (27 × 10). Bootstrap estimates remain conditional on dependence/stationarity assumptions; these are not guaranteed frequentist coverage under every market process.
4. At least **30 completed forward trades** and **30 nonoverlapping calibration clusters** are required. Five-bin expected calibration error must be ≤0.10 and Brier loss must beat the frozen training prior.
5. At least **two known regimes**, each with **15 clusters**, are required; no covered regime may have mean net return below −0.5% per evaluated horizon.
6. The fixed initial portfolio comparison window needs **60 nonoverlapping five-date blocks**, positive candidate net and paired excess lower bounds against all six arms, maximum drawdown ≤10%, and ≥30 ensemble calibration clusters with ECE ≤0.10. Individual and portfolio observations run concurrently and are not described as independent extra datasets.
7. One terminal evaluation occurs after all fixed evidence minima are met. A failed result cannot become passed through favorable repeated peeking. Fixed windows are not expanded until profitable. An unchanged qualified result may still be suspended by later health/calibration monitoring, a release to training, or changed code/artifacts.

States are `RESEARCH_ONLY`, `FORWARD_TESTING`, `INSUFFICIENT_EVIDENCE`, `FAILED`, and `QUALIFIED_FOR_MODEL_PAPER`. Only a source-derived terminal receipt with matching frozen identities and a fresh healthy review can earn Model Paper weight. Entry and fill recheck authorization. There is no public “approve this strategy” or pass/fail override endpoint. Production thresholds and hard risk caps were not lowered.

## Strategy families and redundancy

All 11 tracks remain distinct: momentum, trend following, mean reversion, breakout, volatility, cross-sectional ranking, relative strength, insider/event, macro/regime, statistical relative value and crypto funding/basis.

The fixed baseline versus training-only 1st/99th percentile clipping experiment declared **66 family/class/variant combinations**. **54** were testable; **12** lacked required insider/event or funding/basis history. No price-only substitute was relabeled as event/funding data. Stock, ETF and crypto results are separate, with regime and liquidity breakdowns. Point-in-time market-cap buckets remain unknown where unsupported.

The original **61 studies** contain **30 distinct artifacts**, with no duplicate exact model/asset cohort sets. Their conservative dependence groups are: price trend 37, price reversion 6, price volatility 6, macro 6, mixed price research 6. These are grouping controls, not claims of statistical independence. The retrospective development panel has 108 paired family/class prediction correlations; none has absolute correlation ≥0.90, which does not establish independence in returns or residuals.

No historical study was deleted. The inventory now retains 162 family artifacts, including both experiment versions; 135 nonrepresentative versions are grouped rather than receiving extra votes. **27 current representatives** were selected using development-only normalized MSE plus Brier loss: **18 baseline, 9 clipped**. The first experiment's threshold calculation mistakenly reused final-fold uncertainty; corrected v2 uses each prediction's own prior-fit uncertainty. v1 remains auditable and is superseded, not erased or counted as another independent hypothesis.

A live-start missing-feature dtype bug was corrected and regression-tested. Its initial 27 registrations were superseded by 27 newly frozen definitions before any qualifying outcomes existed. Their records remain intact; the active collector uses only the three current comparison definitions. The 80 added scientific cohorts retain their identities, while the newer registration boundary excludes earlier observations.

## Threshold, ranking and meta-label findings

Historical threshold diagnostics across the 54 testable combinations selected these asset-date rows: **50 → 2,865; 60 → 35; 65 → 4; 70 → 2; 80 → 0**. These totals overlap across correlated models and variants; they are not independent trades or executable fills. No cutoff was selected for historical profit, and no production setting changed. The original live-decision snapshot passed none of the five thresholds once its other observed gates were retained.

Cross-sectional top-1/3/10 research uses three chronological folds and **129 nonoverlapping dates** per comparison, after cost estimates. Baseline stock mean net horizon returns were −0.843%, +0.074%, +0.097%; ETF results were +0.023%, −0.238%, −0.081%. All twelve baseline/clipped top-K return intervals crossed zero. Mean rank correlation was approximately −0.011 for stocks and +0.071 for ETFs. Positive ETF ordering did not establish positive executable portfolio returns. Binary-gate comparisons are recorded alongside ranking; no ranking rule is promoted.

Meta-labeling required 200 primary candidates, 60 nonoverlapping training dates and both outcome classes, after primary fit/calibration and before test. Only ETF momentum in the 2023 fold met the prerequisites (1,039 training candidates over 67 dates). In its 39-date test, the base gate selected 354 rows with mean net horizon contribution +0.032% and interval [−0.073%, +0.130%]. The fixed secondary logistic gate and simple uncertainty gate both selected zero rows. Five other cases lacked prerequisites. There is no demonstrated meta-label benefit; it remains separate from the production selector. No neural networks, reinforcement learning or LLM training were added.

## Historical replay, benchmarks and forward evidence

The final saved replay contains **18 snapshots, 9,036 traces and 618 actual recorded quotes**: 9,018 NO_TRADE traces and 18 DATA_UNAVAILABLE traces. It produced **0 orders, 0 fills, 0 completed trades and $0 P&L**. It uses archived predictions/weights and availability timestamps, never today's model fit to predict the past. It runs in a disposable database, retains missing-data traces, and excludes all results from qualification/training. Only the isolated tests exercise a deliberately positive order → delayed/partial fill → exit → realized P&L path.

Daily historical closes cannot reconstruct spreads/depth or executable quotes. Equity/ETF fill replay still requires historical corporate-action events; it deliberately does not fabricate that adapter. Newly captured quote events enable more meaningful future replay. This is a bounded snapshot debug tool, not a claim of a complete historical execution tape.

Three asset-class comparisons run seven isolated books each: candidate, cash, frozen most-liquid-sentinel buy-and-hold, simple 20-day momentum, RSI mean reversion, equal-weight frozen eligible universe, and prior incumbent (cash if absent). Whole shares, the finite $10,000 budget and missing/invalid quotes can leave benchmark cash uninvested; no frictionless index is silently substituted. Books share the quote-based simulator: spread, 5bps fees, adverse slippage (5bps or 25bps for conservative categories), delay, depth participation, market hours, partial/unavailable fills and portfolio rules. Fresh observed marks are required for evidence; an overnight stale attempt does not replace the last valid session mark.

Metrics include net return, drawdown from initial capital, turnover, fee drag, exposure, concentration, calibration and regime results. Spread/slippage are embedded in fill prices; fee drag alone is not total trading-cost drag. Annualized Sharpe/Sortino-like values require at least 60 consecutive calendar-day returns and otherwise remain unavailable, which is deliberately restrictive for equity calendars.

At acceptance: **27 FORWARD_TESTING; 0 in INSUFFICIENT_EVIDENCE; 0 FAILED prospective terminal trials; 0 qualified.** The 27 active definitions have **0 completed prospective outcomes, 0 independent outcome clusters, 0 completed trades**, and no mature portfolio blocks. There are **141 scientific cohorts total**, including all original 61. No strategy is meaningfully close to qualification: all need the full prospective sample and every tested version failed at least one historical development gate. This is historical rejection of the current test, not proof that the strategy family can never work. Macro representatives in all three classes also currently have no healthy applicable feature snapshots, so their entry participation is suspended.

There is no reliable completion ETA. Five-day outcomes, nonoverlap, market sessions and regime diversity can require substantially more than a year. More credentials cannot accelerate elapsed independent observations. Quarantined samples require retirement, minimum 90-day aging and an explicit reasoned release before future training; release revokes their qualification use and does not start training automatically.

## Verification and preservation



Preserved: **4 credential files unchanged; zero missing or modified prior records; original 61 enrollments; manual and Model Paper accounts; 502 assets; 501 primary archives; 1,280,806 bars**. No LLM runs/tokens/cost, external orders, Git push, account reset or historical-result rewrite occurred. All local data, credentials and runtime files remain ignored.

Methodology references: chronological training must precede test data ([scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)); combinations chosen from many signals can produce serious selection bias ([Novy-Marx, NBER](https://www.nber.org/papers/w21329)); reused holdouts alone do not eliminate backtest overfitting ([Bailey et al., author paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)). These motivate safeguards, not a claim that the current system has solved financial inference.

Acceptance follow-up (October 13, 2026): 27 active definitions, 108 superseded implementation registrations preserved. Replay and pause/resume were exercised in the real production browser. Frozen-model enrollment, retirement and regime attribution were exercised against a disposable fixture with external networking denied. Comparison calculation now runs outside the request loop; replay copies each artifact only once. No numeric qualification criteria were relaxed.
