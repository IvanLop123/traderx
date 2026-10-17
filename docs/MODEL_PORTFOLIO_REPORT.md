# Model selection and automatic paper portfolio — October 11, 2026

## Current result

The existing TraderX repository now has a source registry, dependence-aware
opportunity ranking, deterministic portfolio controls, and a separate automatic
paper book with monitoring, outcomes and attribution. No external order path is
imported by this layer. The app is running locally with **cash as incumbent**.

Current snapshot: **1,450 audited records**, **54 compatible frozen strategy
artifacts**, **zero execution-eligible models**, **502 ranked assets**, **3,514 NO_TRADE
decisions**, **zero orders, fills, no-fill orders or completed production trades**.
The model book is $10,000 cash, 0% return, 0% exposure and 2 observed UTC dates; Sharpe,
Sortino and annualized volatility are intentionally unavailable. This is not
profitable-performance evidence. Production family attribution has zero trades.

The registry has nine fitted families with six variants each: momentum, trend,
mean reversion, breakout, volatility, relative strength, cross-sectional ranking,
macro/regime and predefined pairs/relative value. Insider/event and crypto funding
remain represented in research definitions but did not produce eligible frozen
family artifacts with the needed training coverage. No support or history is fabricated.

## Machine-readable inventory and qualification

The complete private inventory is `data/selection_phase/registry.json`; the durable
copy is the `selection_registry` setting. HTTP `/api/v1/selection/registry` pages
through all rows; `/families` exposes compatible frozen artifacts. Each row links
its source kind/ID/hash, features, universe, target, horizon, time boundaries,
validation, holdout, forward, costs, calibration, conditions, eligibility and reasons.
Unknown fields are explicit rather than inferred as proven facts.

| Source kind | Records |
|---|---:|
| model | 10 |
| ml_study | 25 |
| ml_trial | 1350 |
| cross_study | 2 |
| strategy_study | 3 |
| strategy_model | 54 |
| strategy_comparison | 2 |
| experiment_study | 1 |
| experiment | 2 |
| model_comparison | 1 |

All 1,450 source records enter as challengers; legacy results are labeled already
observed. Fifty-four compatible artifacts have saved stage reviews accessible at
`/api/v1/selection/reviews`. Other model/study types are audit-only until a compatible
frozen inference adapter is supplied. New IDs enter with zero execution weight.

Criteria are frozen with an artifact hash, policy hash, timestamp and cash incumbent:
three chronological walk-forward folds; at least 40 held-out dates; at least 60
independent-date forward observations and 60 challenger portfolio comparison dates;
positive dependence-aware lower bounds; and calibration limits. Outcomes are grouped
by UTC date before a fixed five-date circular block bootstrap (999 draws). Many
cross-sectional asset rows on one date do not count as independent dates.

Portfolio qualification uses a **separate preregistered comparison evidence contract**,
not a requirement that an unqualified model first trade the production model book.
Production automatic outcomes remain monitoring evidence, quarantined from training.
Eligibility receipts are immutable and source-linked; reviews cannot force approval.
A newer eligibility receipt can supersede an earlier failed receipt without rewriting it.

**Qualification boundary:** existing legacy summary formats do not supply the full
prospective walk-forward/holdout/comparison receipt contract. A new preregistered
study and appropriate evidence adapters are still required before any challenger
can pass. This release does not automatically turn old backtests into approval or
silently launch an incumbent-replacing comparison. All challengers may fail. Extra
keys, elapsed time alone, and a high displayed research score do not bypass this.

## Meta-selection and opportunity score

Only one frozen variant per family/class is chosen using development MSE and Brier
comparisons; holdout performance does not select the variant. Related momentum,
trend, breakout, relative-strength and cross-sectional variants share a price-trend
voting group. Reversion/pairs, volatility, macro, insider and funding have separate
conservative groups. Groups are accounting constraints, not proof of independence.

Conditional regime, liquidity and available capitalization observations are shrunk
toward earlier global validation evidence with n/(n+60), requiring at least 30 dates.
Recent completed forward evidence also requires minimum counts before shrinking
weight. A few losses do not delete a strategy. Missing historical market caps,
sector-conditional evidence and correlation-regime results remain unavailable.
Volatility and correlation influence risk/sizing rather than an invented conditional
performance history. Calibration drift uses five predefined probability bins plus
Brier reporting; opposite errors cannot cancel into apparent calibration.

| Component | Maximum points |
|---|---:|
| Expected edge after research costs | 25 |
| Probability | 15 |
| Agreement across dependence groups | 10 |
| Liquidity | 10 |
| Uncertainty | 10 |
| Volatility | 10 |
| Estimated execution costs | 10 |
| Diversification | 5 |
| Freshness/quality | 5 |

Unapproved diagnostic evidence is capped at **25/100** with **zero execution
weight**. Asset details display the components, each vote, health reasons, features'
availability timestamp, downside estimate and costs. Probabilities pooled across
families are descriptive; separate ensemble calibration is part of qualification.
Volatility is explicitly a trailing realized-volatility proxy; downside is an
edge-minus-two-residual-error diagnostic, not a probabilistic loss guarantee.

## Automatic execution and deterministic risk

The `auto_*` ledger and `model_paper_account` are isolated from `manual_*` /
`manual_paper` and `forward_*`. There are no external brokerage imports in
`backend/selection`, no external-order route and no forced-eligibility UI. The same
local simulator handles market hours, bid/ask freshness, five-second minimum delay,
spread, adverse slippage, fees, depth participation, partial fills and expiry.
No historical close or midpoint becomes a guaranteed fill.

Controls are validated in `config/model_portfolio.json` and cannot be bypassed by
forecast output. Defaults: 10% per asset; 30% sector; 60% class; 30% contributing
group; 25% correlated cluster; 80% gross exposure; eight positions; 10% drawdown;
0.01% average daily dollar volume; score ≥65; probability ≥55%; two eligible groups.
Pending buys reserve cash and concentration capacity; pending sells grant no credit.
Unknown sector is a common bucket, not zero exposure. Unknown correlations receive
full correlation penalties. Ninety-date Pearson correlations need 60 paired dates;
no unstable inverse covariance optimization is used.

Simple volatility-targeted and capped confidence-weighted sizing discount uncertainty.
Fresh quote costs replace earlier research costs at decision time and are rechecked
at fill time. Model hashes, stale inputs, available cash, exposure and drawdown are
rechecked before buys fill. Stale holdings or corporate-action review block new
entries. Stops are quote-triggered requests, not guaranteed prices. Default exits
are five equity sessions / five elapsed crypto days, with protective data, drawdown
and maximum-duration exits. Pause blocks entries while exits and accounting continue.

Snapshots preserve exact features available at the decision, model/data hashes,
prediction/uncertainty, vote weights, regime, score components, costs, sizing reasons,
intended orders, later fills and outcomes. Partial exits aggregate into one completed
entry outcome. MFE/MAE use observed bid quotes only. Attribution allocates P&L by
recorded family weight and is explicitly not causal. Full automatic fill history is
used for accounting; UI lists are bounded independently.

## Bounded chronological sizing/exit comparisons

Exactly 14 fixed policies: two sizing rules × seven exit rules. A transparent
20-session momentum reference on 24 fixed assets isolates these choices. Three
chronological windows: 2020–2022, 2022–2024, 2024–April 16, 2025. The final diagnostic
window is April 16, 2025–October 10, 2026 (542 observed dates). Definitions are saved
before computing comparisons. This already-inspected historical window is **not a
new independent holdout**. No winner was promoted, and defaults were not retuned.

| Sizing | Exit | Three chronological returns | Final diagnostic return | Drawdown | Completed trades |
|---|---|---|---:|---:|---:|
| volatility targeted | fixed horizon | -3.93%, -8.53%, -4.75% | -2.11% | 3.90% | 550 |
| volatility targeted | signal reversal | 2.68%, 0.27%, 3.61% | 1.24% | 2.77% | 265 |
| volatility targeted | score decay | 2.68%, 0.27%, 3.61% | 1.24% | 2.77% | 265 |
| volatility targeted | risk stop | 2.60%, 1.31%, 3.75% | 5.73% | 2.82% | 182 |
| volatility targeted | volatility stop | 2.44%, 1.81%, 2.83% | 5.96% | 2.73% | 209 |
| volatility targeted | profit target | 6.39%, 5.91%, 5.65% | 3.11% | 2.33% | 163 |
| volatility targeted | trailing | 5.24%, 1.90%, 1.40% | 3.68% | 2.47% | 216 |
| confidence capped | fixed horizon | 0.84%, -9.78%, -2.34% | 3.01% | 5.21% | 566 |
| confidence capped | signal reversal | 17.24%, -2.13%, 2.61% | 5.75% | 4.66% | 266 |
| confidence capped | score decay | 17.24%, -2.13%, 2.61% | 5.75% | 4.66% | 266 |
| confidence capped | risk stop | 11.93%, 2.89%, 7.41% | 9.87% | 4.61% | 191 |
| confidence capped | volatility stop | 17.17%, 10.01%, 1.95% | 11.03% | 4.81% | 215 |
| confidence capped | profit target | 25.58%, 7.83%, 5.97% | 7.81% | 4.93% | 167 |
| confidence capped | trailing | 5.86%, 4.25%, 6.74% | 12.67% | 3.04% | 227 |

These are marked research returns with subsequent daily-open price proxies and
adverse costs, not actual executable fills. They do not reproduce every live quote,
sector/correlation constraint or corporate-action edge case. They retain retrospective
membership and adjusted-vintage biases. The results cannot justify a profit claim.
Signal reversal and score decay coincide for this fixed binary reference signal;
they are not independent discoveries. Exposure is small and cash is included.

## Monitoring and UI

Overview leads with Model Paper Portfolio, holdings, opportunities, development
leaders, exposure and warnings. Scanner has class, regime, liquidity, score and
eligibility filters. Asset detail exposes score/votes. Strategy pages keep historical,
holdout and forward evidence separate. Model portfolio shows completed trades,
performance samples, concentration, fees and attribution. Manual buying remains an
explicit, separate experiment.

In-app alerts cover new leaders, disagreement, strategy degradation, new model IDs,
feature/missingness/input health, prediction shifts and drawdown. Required data
errors fail closed. Schema failures in providers remain visible through the existing
provider-monitoring pipeline. No external notifications were enabled.

Daily equity marks do not multiply sample counts with every poll. Annualized measures
require at least 60 consecutive daily returns and no stale marks, use a declared
365-day mixed-asset basis, and remain exploratory even then. Regime/liquidity/family
metrics always carry trade counts. Account equity includes supported corporate
receivables; per-trade fill attribution does not separately allocate dividends.

## Acceptance and preservation

## Remaining limits and what is next

The engineering surface is usable for research and paper simulation; it is not a
validated profitable trader. No challenger currently qualifies. Completing genuinely
independent qualification takes new preregistered observations and source-linked
portfolio comparison adapters, not a setting that re-labels old results. The fixed
minimums and shrinkage rules are conservative design choices, not statistical proofs.
Multiple-testing and overlapping-market dependence still limit inference.

Survivorship-free membership, verified delisting returns, historical market caps,
sector/correlation conditional evidence, tick/queue execution, full lifecycle coverage,
and new asset-class execution remain incomplete. Cached provider vintages and sampled
quotes cannot reconstruct everything that happened. Closed markets, sleep, outages,
missing entitlements and depth limitations can legitimately prevent fills.

## Method and dependency references

Selection bias from trying many strategies motivates keeping the trial inventory
and avoiding winner-based claims; this release does not claim to implement a
Deflated Sharpe calculation. [Bailey and López de Prado](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).
Brier is not pure calibration error; calibration and discrimination require separate
interpretation. [scikit-learn calibration documentation](https://scikit-learn.org/stable/modules/calibration.html).
Covariance estimation noise motivates conservative exposure limits here; a shrinkage
covariance estimator is not implemented. [Ledoit and Wolf](https://ledoit.net/honey.pdf).
The dependency audit prompted compatible updates for
[Next.js](https://github.com/advisories/GHSA-4jqv-mc3x-m676),
[sharp](https://github.com/advisories/GHSA-wq5f-xc86-pv6w), and
[source-map-js](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).
