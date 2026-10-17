# TraderX historical expansion and forward-study report

Audit date: 2026-10-09. Permanent project: `/Users/ivanlopez/Desktop/traderx`.

Implemented: 24-asset configurable universe, versioned historical series, publication-aware evidence, cross-sectional comparison, and isolated hypothetical forward portfolios. **No model passed promotion. No external order or paid language-model call was made.**

## Exact daily price coverage

Counts below are distinct daily bars in the primary research series; raw and adjusted copies are not counted twice. Equity/ETF bars use Alpaca historical SIP with `adjustment=all`; separate `raw` SIP archives support liquidity and execution. Crypto is raw Coinbase Exchange data.

| Asset | Before bars | Before start | After bars | After start | Latest bar |
|---|---:|---|---:|---|---|
| AAPL | 501 | 2024-10-08 | 2,707 | 2016-01-04 | 2026-10-08 |
| MSFT | 501 | 2024-10-08 | 2,707 | 2016-01-04 | 2026-10-08 |
| NVDA | 501 | 2024-10-08 | 2,707 | 2016-01-04 | 2026-10-08 |
| JPM | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| JNJ | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| XOM | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| WMT | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| CAT | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| NEE | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| SPY | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| QQQ | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| IWM | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| MDY | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| IJR | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| XLF | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| XLV | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| XLE | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| XLI | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| XLU | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| XBI | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| URA | 0 | — | 2,707 | 2016-01-04 | 2026-10-08 |
| BTC-USD | 1,106 | 2023-09-29 | 4,099 | 2015-07-20 | 2026-10-08 |
| ETH-USD | 1,106 | 2023-09-29 | 3,794 | 2016-05-18 | 2026-10-08 |
| SOL-USD | 1,106 | 2023-09-29 | 1,940 | 2021-06-17 | 2026-10-08 |

Total primary daily rows: **4,821 → 66,680**. Requested equities from 2016-01-01 and Coinbase from 2015-01-01; first returned dates reflect actual provider availability. Missing/no-trade intervals were not invented.

Universe: 9 stocks (AAPL, MSFT, NVDA, JPM, JNJ, XOM, WMT, CAT, NEE), 12 ETFs (SPY, QQQ, IWM, MDY, IJR, XLF, XLV, XLE, XLI, XLU, XBI, URA), and BTC/ETH/SOL. Mid-cap, small-cap and thematic exposure is represented by ETFs; this is not yet a broad individual small-cap stock archive.

Archived current listing metadata: 14,400 active and 19,169 inactive instruments. These snapshots do **not** establish historical membership or delisting returns. Historical survivorship bias remains a stated limitation.

## Corporate actions and price semantics

Raw and adjusted series have separate hashes/manifests; mixing is rejected. Provider corporate-action records are retained separately, without claiming their process date is an announcement timestamp. A source check showed:

| Asset / date | Raw close return | Adjusted close return |
|---|---:|---:|
| AAPL 2020-08-31 | -74.15% | 3.39% |
| NVDA 2021-07-20 | -75.22% | -0.86% |
| NVDA 2024-06-10 | -89.93% | 0.75% |

These checks verify that the retrieved adjusted series removes large split discontinuities. Adjusted prices remain retrospective provider vintages and are never assumed executable.

## Macro first-release coverage

Before counts include missing-value rows where returned by the earlier provider call; after counts below include only numeric first releases.

| Series | Before source rows | Before observation start | After numeric releases | After observation range |
|---|---:|---|---:|---|
| FEDFUNDS | 57 | 2022-01-01 | 201 | 2010-01-01 → 2026-09-01 |
| UNRATE | 57 | 2022-01-01 | 200 | 2010-01-01 → 2026-09-01 |
| T10Y2Y | 1,244 | 2022-01-03 | 3,178 | 2014-01-27 → 2026-10-08 |
| CPIAUCSL | 56 | 2022-01-01 | 199 | 2010-01-01 → 2026-08-01 |
| INDPRO | 56 | 2022-01-01 | 200 | 2010-01-01 → 2026-08-01 |
| M2SL | 56 | 2022-01-01 | 200 | 2010-01-01 → 2026-08-01 |
| BAMLC0A0CM | 793 | 2023-10-10 | 784 | 2023-10-10 → 2026-10-08 |

Initial releases are available only after the next New York midnight following their recorded release. No revised latest-vintage values were backfilled into early predictor rows. Earlier T10Y2Y/credit-spread archive windows returned unavailable; no substitute history was fabricated. Previously captured credit-spread releases are retained when the provider’s rolling history no longer returns them. Historical index rebasing and short credit-spread coverage remain limitations of these simple level/change candidates.

## SEC evidence

| Asset | Historical Form 4 documents | Transaction rows | First publication in retrieved window | Amendments | Valid aligned daily rows |
|---|---:|---:|---|---:|---:|
| AAPL | 250 | 716 | 2021-02-04T04:39:29+00:00 | 1 | 1,342 |
| MSFT | 250 | 302 | 2024-12-02T23:02:19+00:00 | 1 | 423 |
| NVDA | 250 | 1,291 | 2024-06-13T21:52:15+00:00 | 0 | 541 |

Previously there was only a short observed-time document stream, with no defensible reconstructed historical Form 4 feature window. All 750 requested historical documents were retrieved; older filings beyond the per-issuer cap remain uncollected. Features now include nonderivative purchase candidates/dollars, explicitly confirmed open-market count, distinct-insider clustering, role weighting, repeated buyers and days since filing. Issuer CIK must match the asset; publication gates, warmup and unresolved amendment windows are enforced. P alone does not prove an open-market transaction. Gifts, exercises, awards, explicit private placements and planned transactions are excluded.

None of these SEC families yet meets the early training-fold coverage/nonconstant requirements for the expanded six-asset comparisons. AAPL’s retrieved transactions contain no nonderivative code-P purchases. Historical 13F training features remain excluded because the required defensible security mapping and comparable historical coverage are absent.

| Crypto asset | Historical funding records | First source timestamp | Last source timestamp | Aligned daily rows |
|---|---:|---|---|---:|
| BTC | 29,353 | 2023-05-12T00:00:00.048000+00:00 | 2026-10-09T18:00:00.061000+00:00 | 1,219 |
| ETH | 29,353 | 2023-05-12T00:00:00.048000+00:00 | 2026-10-09T18:00:00.061000+00:00 | 1,219 |
| SOL | 29,353 | 2023-05-12T00:00:00.048000+00:00 | 2026-10-09T18:00:00.061000+00:00 | 1,219 |

Funding and the source premium field are real historical observations. No historical open interest or actual spot/perpetual basis was reconstructed from current snapshots. Paid funding is not spot cash flow. These families remain excluded from the long early training folds because of insufficient coverage; collection continues.

EIA retail-price observations are preserved. Energy/utility exposures exist in the new universe, but verified publication vintages and a validated sector-specific feature mapping are still absent. No EIA predictor was forced into unrelated assets.

## Per-family aligned coverage and eligibility

The following shows the number of rows with at least one available numerical feature in each family, not the number of independent outcomes. Eligibility shown is a representative training-window screen; every model fold repeats coverage, nonconstant and redundancy selection using only its training rows. The UI gives dates, missingness, provider and reasons for all 24 assets.

## Frozen algorithm and target comparisons

Per asset: Ridge/logistic (alpha 10 or 100, C 0.1 or 0.01), random forest (60 trees, depth 3/5, minimum leaf 25/40), histogram gradient boosting (60 iterations, 5/9 leaves, L2 10/30). Three targets (positive, after-cost, volatility-scaled meaningful move) × horizons 1/5/10 × six parameter configurations = 54 declared trials per asset, 324 total, plus fixed-estimator feature-family ablations. No neural networks or reinforcement learning.

Development uses three expanding chronological folds, separate purged probability calibration, horizon-plus-delay gaps and nonoverlapping final test windows. All selections were frozen before one-time final holdout release. Older research already inspected some overlapping historical dates; only new forward observations can supply fresh untouched evidence.

| Asset | Selected algorithm / target / bars | Families | Independent holdout windows | MSE / zero MSE | Brier / base Brier | Strategy net return | Buy & hold |
|---|---|---|---:|---:|---:|---:|---:|
| BTC-USD | linear / meaningful_move / 1 | price | 273 | 1.0050 | 0.9983 | 0.00% | 43.49% |
| ETH-USD | linear / after_cost / 1 | price | 252 | 1.0104 | 1.0089 | 0.00% | 15.53% |
| SOL-USD | linear / after_cost / 10 | price | 32 | 1.1211 | 1.0105 | 0.00% | -50.48% |
| AAPL | linear / positive / 5 | price | 77 | 1.0076 | 1.0300 | -3.23% | 51.57% |
| MSFT | linear / meaningful_move / 5 | price, regime, technical | 77 | 1.0339 | 0.9750 | 0.00% | 30.15% |
| NVDA | linear / positive / 1 | price | 180 | 0.9981 | 1.0064 | -26.27% | 100.65% |

Ratios below 1 beat the named forecast benchmark for that diagnostic only. Historical trading uses delayed open-price proxies and explicit estimated costs, not verified executable quotes. There is no claim of deployable profitability.

### Ablations (development objective; lower is better)

| Asset | Price | + Technical | + Technical + Regime | + Cross asset | + Macro | SEC / funding addition |
|---|---:|---:|---:|---:|---:|---|
| BTC-USD | 1.0170 | 1.0553 | 1.0601 | 1.0653 | 1.9125 | No eligible additional early-fold features |
| ETH-USD | 1.0237 | 1.0892 | 1.1214 | 1.0437 | 2.4138 | No eligible additional early-fold features |
| SOL-USD | 0.9917 | 1.0192 | 1.1110 | 1.0286 | 1.5633 | No eligible additional early-fold features |
| AAPL | 0.9962 | 1.1123 | 1.1410 | 1.0480 | 2.7478 | No eligible additional early-fold features |
| MSFT | 1.0314 | 1.0286 | 1.0163 | 1.0841 | 1.2334 | No eligible additional early-fold features |
| NVDA | 1.0141 | 1.0681 | 1.0798 | 1.0855 | 1.5664 | No eligible additional early-fold features |

MSFT’s technical/regime family combination improved its development objective, but did not establish a superior held-out trading result. All other selected models retained price features only. Macro additions degraded development results despite their newly adequate historical coverage.

### Cash decisions

| Asset | Weak probability ≤ 0.50 | Probability 0.50–0.55 | Nonpositive net edge | Eligible entry windows |
|---|---:|---:|---:|---:|
| BTC-USD | 273 | 0 | 139 | 0 |
| ETH-USD | 252 | 0 | 108 | 0 |
| SOL-USD | 0 | 32 | 7 | 0 |
| AAPL | 1 | 21 | 7 | 55 |
| MSFT | 77 | 0 | 40 | 0 |
| NVDA | 0 | 0 | 95 | 85 |

Reasons overlap. Thresholds were not relaxed to manufacture trades. AAPL and NVDA traded in historical simulations and lost money; the other four stayed in cash. Missing current features/eligibility also cause cash in forward studies.

## Cross-sectional results

21 US equities/ETFs; individual, class-pooled and pooled Ridge/logistic, forest and boosting comparisons. Development selected **pooled linear**. Each final comparison contains **1,449 asset rows but only 69 independent date clusters**. Targets are five-session relative future return and probability of outperformance.

| Scope / algorithm | Holdout MSE / zero | Brier / base | Mean rank correlation | Top-rank mean return after assumed costs |
|---|---:|---:|---:|---:|
| individual / linear | 1.0274 | 1.0074 | -0.0134 | 0.773% |
| individual / forest | 1.0244 | 1.0047 | 0.0035 | 0.438% |
| individual / boosting | 1.0621 | 1.0434 | -0.0187 | 0.938% |
| asset_class / linear | 1.0072 | 1.0046 | -0.0148 | 0.498% |
| asset_class / forest | 0.9977 | 0.9992 | -0.0019 | 0.353% |
| asset_class / boosting | 1.0091 | 1.0059 | -0.0077 | 1.156% |
| pooled / linear | 1.0008 | 0.9981 | 0.0150 | -0.032% |
| pooled / forest | 0.9920 | 0.9974 | 0.0253 | 1.194% |
| pooled / boosting | 0.9918 | 0.9999 | 0.0145 | 0.984% |

The development-selected pooled linear model did not beat zero-relative-return MSE and its top-rank return diagnostic was negative. Some tree diagnostics were better on the released holdout; choosing them now would be post-holdout selection, not a new validated improvement. Equal-weight mean return after assumed costs was 0.119% per evaluation window; cash was 0%. Top-rank means are not portfolio compound returns, have no executable-price guarantee, and are not proof of significance. All approaches remain research-only.

## Forward operation and remaining limits

Six new frozen model cohorts are enrolled with independent hypothetical cash books. They wait for new completed features after enrollment. They have no fabricated historical decisions, fills or outcomes. Fresh bid/ask quotes with verified depth, latency, sessions, fees, slippage, position limits and partial/unavailable fills are used. Cash decisions also collect subsequent observations. Positions, decisions, exact features, fills, P&L, observed excursions and attribution are available under Portfolio → Forward studies.

## How to use it

1. Double-click `TraderX.command` in the Desktop `traderx` folder. Keep its window open. Open http://localhost:3000.
2. Use **System → Data coverage** for assets, dates, missingness and exclusion reasons. The universe editor saves validated runtime settings.
3. Use **Models** for the saved comparisons, ablations, benchmark failures and cash reasons. Running a new comparison consumes local CPU, not language-model tokens.
4. Use **Portfolio → Forward studies** to view the six enrolled cohorts. New observations require real elapsed market time. Additional frozen models may be enrolled deliberately.
5. Leave the Mac awake and TraderX running to collect forward evidence. Closing it creates a real observation gap; missed forward fills are never reconstructed later.
6. No additional keys or payment are required for this delivered phase. Optional missing entitlements remain excluded. Do not enable live trading to run research.

## Final acceptance

- **200 backend tests and 8 subtests passed**, including the dedicated PostgreSQL checks.
- **45 frontend integration checks passed**; production build and TypeScript checks passed.
- New coverage and forward-study pages reviewed in the browser at desktop and 390px width. Tables scroll within their panels; the page does not overflow.
- Corporate-action, publication timing, first-release alignment, missing/duplicate data, timestamp, eligibility, provider pagination, partial-fill, session, cash-outcome and quarantine regressions passed.
- Python dependencies, environment checks and read-only provider checks passed.
- Working tree, Git index and reachable-history secret audit passed. `.env` and protected key files have matching before/after hashes; nothing was pushed.
- AI Off: **0 calls, 0 tokens, $0**. Live trading false; external paper/demo submission disabled; global paper halt preserved.
- Six fresh forward cohorts enrolled; **0 forward decisions/fills at acceptance**, correctly waiting for observations after enrollment. No model promoted.

Nonoverlapping windows/date clusters reduce overlap; they are not a claim that financial observations are statistically independent. This phase improves documented data coverage and research controls. It does not demonstrate a profitable trading system.

Evidence files are kept privately under `data/universe_phase/`: `before.json`, `after.json`, `backfill.json`, `extended.json`, `model_results.json`, `cross_results.json`, corporate-action checks and test logs. They and all raw data remain outside Git. The checked-in summary contains no credentials.
