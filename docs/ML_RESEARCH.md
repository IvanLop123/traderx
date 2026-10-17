# TraderX research phase — October 9, 2026

The research application is running in the existing Desktop/traderx repository. This phase strengthens evaluation and data handling; it does not establish a profitable or production-qualified trading model. All six new challengers remain research-only. No live/external order execution or paid language-model request was enabled.

## Start and use

Double-click `TraderX.command` in the Desktop/traderx folder, then open http://localhost:3000. Keep the launcher window open. Ctrl-C in that window stops the services it started. Keep the Mac awake and the app running for collection and scheduled checks; there is no cloud service running when the computer is off.

Use Overview for warnings and market state, Assets/Scanner for the six-asset universe, Models for the saved comparisons, and System for provider status, coverage and worker decisions. Model details expand into ablations, exact inputs, benchmarks and limitations. Research retains backtests, experiments, filings, macro, prediction markets and specialist tools. Portfolio remains an internal paper account. Settings remains AI Off.

Scheduled local statistical retraining is enabled for BTC, ETH, SOL, AAPL, MSFT and NVDA: checked hourly, no more often than every seven days, after at least seven new completed daily bars. The earliest next scheduled baseline runs are October 15, subject to new data and freshness. This is not continuous 24/7 fitting and does not train language-model weights. The six existing baseline forward studies continue collecting future evidence; the new richer comparisons are historical challengers, not yet enrolled as executable or prospective models.

## 1–3. Provider fixes

**Alpaca:** the actual IEX quote response was HTTP 200 with a valid object but a positive bid and zero ask/ask size after the market session. The old adapter tried to construct an invalid two-sided quote and reported a generic shape error. The adapter now distinguishes missing quotes, crossed quotes, malformed data, authentication, entitlement, unsupported endpoints and rate limits. A missing quote does not stop daily-history ingestion. System shows working history with the quote limitation when relevant. During the October 9 session, real two-sided AAPL/MSFT/NVDA quotes and history were available. Historical closes are displayed separately when there is no quote; they never become executable quotes. Sanitized regression fixtures cover both cases.

## 4–5. Algorithms, targets and finite search

Local scikit-learn models now compared: standardized Ridge regression + logistic classification; seeded random-forest regression/classification; seeded histogram-gradient-boosting regression/classification. A separate standardized Ridge forecast estimates future mean squared daily log returns. No new XGBoost/LightGBM dependency, unjustified ensemble, pooled asset-class model or regime-specific estimator was added. Current data does not support claiming these would help; asset-specific comparisons and regime diagnostics are available.

Each asset registers 54 configurations: six bounded parameter choices × horizons 1/5/10 daily bars × three classifier targets. Crypto had 54 valid trials each. Stocks had 36 valid trials each; their 10-bar trials were recorded as insufficient data. Seed 1729; forests use 60 trees, boosting 60 iterations; one numerical compute thread per comparison. Six studies recorded 324 trials, 270 evaluated successfully and 54 marked insufficient data. Family ablations run first with the same simple five-bar linear model. All attempted configurations remain auditable.

For bar i and horizon h, the return target is open[i+h+2]/open[i+2] − 1. Decisions wait one full completed bar after the signal is available before entering at the second subsequent open. Classification targets are: return above zero; above assumed round-trip cost; above max(round-trip cost, half the past 20-bar log-return standard deviation × sqrt(h)). Expected return and realized-variance forecasts are separate numerical outputs. Default illustrative costs are 5 bps fee + 5 bps slippage + half a 2 bps spread on each side: 22 bps round trip. These are configurable research assumptions, not verified account-specific execution costs; crypto fees and market impact may be higher.

## 6–8. Actual inputs and provider contribution

The audit before modification is `docs/ML_AUDIT_BEFORE.md`. The prior six baseline models used exactly eight OHLCV-derived inputs; connecting an API had not made its contents part of those fits. Those existing artifacts and forward studies are preserved.

Final selected challengers:

| Asset | Selected algorithm | Target | Horizon | Actual features / families | Actual source |
|---|---|---|---|---|---|
| BTC-USD | Ridge + logistic | Return > 22 bps | 1 daily bar | 3: price | Coinbase OHLCV |
| ETH-USD | Random forest | Return > 22 bps | 1 daily bar | 3: price | Coinbase OHLCV |
| SOL-USD | Random forest | Return > volatility/cost threshold | 1 daily bar | 3: price | Coinbase OHLCV |
| AAPL | Random forest | Return > volatility/cost threshold | 1 daily bar | 3: price | Alpaca IEX OHLCV |
| MSFT | Random forest | Return > 0 | 1 daily bar | 21: price, technical | Alpaca IEX OHLCV |
| NVDA | Random forest | Return > 22 bps | 1 daily bar | 3: price | Alpaca IEX OHLCV |

BTC, ETH, SOL, AAPL and NVDA each use exactly `return_1`, `return_5`, `return_20`. MSFT uses those three plus `realized_volatility`, `volume_zscore`, `vwap_distance`, `rsi`, `bollinger_z`, `gap_return`, `intraday_return`, `acceleration`, `range_location`, `atr_fraction`, `macd_fraction`, `bollinger_width`, `ma20_to_ma60`, `volume_change_5`, `signed_volume`, `drawdown_60`, `vol_of_vol`, `trend_efficiency` (21 total).

The modular pipeline additionally offers cross-asset relative momentum, correlations/correlation changes and relative volatility; past-only trend, volatility, selected-peer risk breadth and liquidity-stress proxies; and ALFRED initial-release levels and 20-bar changes for FEDFUNDS, UNRATE, T10Y2Y, CPIAUCSL, INDPRO, M2SL and BAMLC0A0CM. FRED/ALFRED and Coinbase/Alpaca cross-asset history actually entered eligible ablation fits. They were not retained in the six final selections because their tested combinations performed worse on development data. A connected feed is not counted as a selected predictor merely because it was tested.

SEC deterministic features preserve actual observation/publication timing and add insider officer/director purchases, repeat buyers and purchase clusters to existing count/dollar/activity windows. Their collected history is too short for the training coverage threshold, so no current selected challenger uses them. No historical Form 4 backfill or guessed 13F CUSIP mapping was manufactured. Institutional ownership-change features still need an eligible, mapped historical series.

## 9–10. Validation and leakage controls

Frozen datasets contain 1,106 daily bars per crypto asset (2023-09-29 through 2026-10-08) and 501 per stock (2024-10-08 through 2026-10-07). The final 20% was reserved during family, target and parameter selection. Development uses three expanding chronological folds. Every fold has separate fitting, calibration and validation blocks, with h+2-bar gaps so fit/calibration labels end before the next block. Validation/test predictions are sampled every h+2 bars and do not have overlapping outcomes. No random time-series shuffle is used.

Coverage, constant removal, 98%-correlation pruning, median imputation and scaling use fitting rows only. A feature requires at least 80% fitting coverage. Missing unavailable families do not become fabricated zeros. Cross-asset joins are backward by completed-bar availability, with a four-day tolerance; stale equity returns are not repeated across weekend observations. Structured evidence uses its persisted and declared availability plus expiry. ALFRED output-type-4 initial releases are archived; availability is conservatively delayed to the next New York midnight after release. Current revised macro values are not backfilled. Future/uncompleted bars are excluded.

Classifier sigmoid calibration is fitted on the separate purged calibration block. Reported Brier score, base-rate Brier, reliability bins, calibration gap, precision/recall, AUC and direction accuracy distinguish calibrated construction from actual calibration quality. A forecast probability is not confidence in profit. Return uncertainty is a development residual standard deviation, not a guaranteed interval.

The comparison score averages normalized return MSE and normalized Brier loss across three folds (simple paired benchmark = 1; lower is better). Family and parameter selection still make development estimates optimistic. The six reserved holdouts were released once only after choices were frozen; subsequent tuning was not performed on them. Reopening a result is not new evidence. Historical dates had already appeared in older baseline research, so these are not globally pristine datasets. Prospective validation remains mandatory. Selected-universe survivorship bias, downloaded-price revisions and raw equity corporate actions remain explicit limitations.

## 11. Feature ablations

Same five-bar positive-return linear baseline throughout this table. Lower is better; scores are development estimates, not final test results.

| Asset | Price | + Technical | + Cross-asset | + Macro | All available |
|---|---:|---:|---:|---:|---:|
| BTC-USD | 1.045 | 1.310 | 1.086 | 6.436 | 5.302 |
| ETH-USD | 1.071 | 1.383 | 1.112 | 2.661 | 1.999 |
| SOL-USD | 1.059 | 1.164 | 1.095 | 2.483 | 2.626 |
| AAPL | 1.875 | 1.940 | 2.131 | 25.852 | 14.159 |
| MSFT | 1.591 | 1.293 | 2.780 | 3.347 | 2.103 |
| NVDA | 2.138 | 4.797 | 3.154 | 5.611 | 2.604 |

Technical inputs improved MSFT development loss but did not survive its holdout. Price-only won the family comparison elsewhere. Added macro/cross-asset combinations hurt all six in this bounded test; this does not prove those sources are universally useless. SEC/funding combinations with zero eligible added inputs reproduce price-only and are not evidence of a tested benefit. Three development block shifts per feature supply importance and dispersion. Highest measured contributions were BTC return_5, ETH return_20, SOL return_5, AAPL return_5, MSFT bollinger_z, NVDA return_20; importance is not causation and is unstable in small samples.

## 12–13. Reserved tests and promotion

Crypto holdout: 2026-03-01 through 2026-10-08, 73 independent evaluated windows. Stock holdout: 2026-05-14 through 2026-10-07, 33 windows. Outcomes require the entry delay and future exit, so not every trailing bar can be scored. All selected horizons were one bar.

| Asset | Development score | Holdout return MSE / zero forecast | Brier / base rate | Calibration gap | Net strategy | Buy & hold |
|---|---:|---:|---:|---:|---:|---:|
| BTC-USD | 0.9997 | 0.000335 / 0.000332 | 0.2450 / 0.2460 | 2.27% | 0.00% | 24.30% |
| ETH-USD | 1.0027 | 0.000556 / 0.000539 | 0.2635 / 0.2493 | 14.25% | 0.00% | 33.34% |
| SOL-USD | 1.0061 | 0.000664 / 0.000685 | 0.1924 / 0.1949 | 0.74% | 0.00% | 39.10% |
| AAPL | 1.0054 | 0.000214 / 0.000204 | 0.2031 / 0.1984 | 6.43% | 0.00% | 10.45% |
| MSFT | 0.9724 | 0.000478 / 0.000471 | 0.2670 / 0.2430 | 16.93% | 0.00% | 27.39% |
| NVDA | 0.9581 | 0.000371 / 0.000401 | 0.2545 / 0.2504 | 12.63% | 0.00% | 5.28% |

No selected strategy traded: predicted returns had to exceed costs and the selected-target probability had to exceed 55%. Zero simulated return therefore means cash, not demonstrated alpha. SOL improved both loss benchmarks, but has too few independent outcomes and no positive strategy return; NVDA improved return MSE but not Brier. BTC narrowly improved Brier but not return MSE. ETH/AAPL/MSFT did not improve either paired holdout baseline. All remain research-only.

Comparable delayed-entry trading baselines, after the same costs:

| Asset | Always cash | Long each window | Momentum | Mean reversion | Continuous buy & hold |
|---|---:|---:|---:|---:|---:|
| BTC-USD | 0.00% | -9.61% | -9.08% | -6.69% | 24.30% |
| ETH-USD | 0.00% | -13.13% | -10.88% | -7.63% | 33.34% |
| SOL-USD | 0.00% | -2.65% | 8.91% | -4.83% | 39.10% |
| AAPL | 0.00% | -1.25% | -1.84% | 0.04% | 10.45% |
| MSFT | 0.00% | 2.41% | 2.51% | 0.44% | 27.39% |
| NVDA | 0.00% | 6.92% | 7.36% | 5.09% | 5.28% |

Return/direction/probability diagnostics, linear/logistic benchmarks, daily marked-equity drawdown, Sharpe-like statistics, turnover, trade quantiles and trend/volatility/risk-on/off slices are retained in each study. Selected strategies have zero trades, zero drawdown and undefined Sharpe, not an infinite or flattering ratio. Buy-and-hold has different exposure duration and is shown explicitly alongside window-matched benchmarks. Cash interest, taxes, account-tier commissions, impact and fills are not fully modeled.

Promotion still requires at least 200 nonoverlapping holdout observations, beating zero-return and base-rate forecasts, usable calibration, at least matching the simple linear return model, positive net return, beating buy-and-hold, and new future validation. Every historical challenger is hard-limited to research-only; none is sent to the existing execution/model-promotion registry automatically. Existing baseline promotion requirements were not weakened. NO_TRADE remains normal.

## 14. Retraining and reproducibility

Durable leases prevent simultaneous duplicate asset comparisons. Content fingerprints reuse saved comparisons for unchanged inputs, excluding arrival-only metadata. Each study stores configuration, seed, frozen data/matrix, exact feature set, exclusions, fitted-training medians, all trial outcomes and a one-time holdout state. Reserved inputs are blocked from generic record/evidence endpoints. Failed comparisons retain the previous baseline.

The scheduled worker records last data observation, attempted/successful training dates, new bars, next eligible date, input fingerprint, range, counts, excluded features, model version and validation gates. With comparison enabled, a due successful baseline fit also produces the bounded comparison, whose holdout stays locked. Checking the schedule repeatedly is not repeated training. Existing baseline models/artifacts, saved experiments and shadow studies remain intact.

## 15–16. UI and visual review

Eight primary destinations: Overview, Scanner, Assets, Models, Research, Portfolio, System, Settings. Specialist pages remain reachable under section navigation. Overview surfaces paper equity, model qualification, warnings, market regime, data freshness and recent evidence. Models show targets/horizons, fitting/calibration/validation periods, benchmark scores, actual inputs, probabilities/uncertainty, reasons for failure and the lack of forward enrollment. System uses concise provider cards with expandable diagnostics, data coverage and worker decisions. Low-level tools are retained under expandable sections.

The primary theme is espresso (#17120F background, #211915 surfaces, #44342B borders, #B48768 accent, #F2EAE4 text, #B9AAA0 secondary text). Green is retained only for semantic positive/working states. Mobile navigation has text labels; wide tables scroll within their panels. Main screens were reviewed at desktop and 390px phone width, with no document-level horizontal overflow or observed browser console errors. App title/icon/metadata use TraderX branding; necessary provider/library references remain functional configuration, not authorship stamps.

## 17. Acceptance checks

## 18–20. Limits, preservation and next actions

The app can collect and test data now. It cannot make weak historical evidence reliable by adding keys. Leave it running to collect future bars/filings/funding and let scheduled checks decide whether retraining is due. Compare saved results in Models before running new searches. More searches on already inspected history increase overfitting risk; they do not create fresh evidence.

Future research work requires adjusted corporate-action-aware histories, historical universe membership, defensible longer filing/institutional histories and mappings, relevant energy/event mappings, richer venue-specific costs and sufficient future observations. New challenger model serialization/forward enrollment and class/regime pooling or ensembles require separate design and evidence; they were not silently added to execution. Advanced semantic document extraction and local assistant/fine-tuning remain postponed by request. Docker deployment was not exercised; this handoff is the verified native Mac runtime.

The original `.env` and all three pre-existing key files matched their pre-phase SHA-256 values. Existing databases and model/experiment history were preserved; new records were appended. Secrets, local databases/models, caches and build outputs remain ignored by Git. No push, publication, trade, transfer or billable LLM call was made. All live/external trading flags remain disabled.

## Saved study identities

- BTC-USD: `740d569f14f206541aa6762c363cf3fd837f04f87102c32bd8cbe74fe2a2b442`; parameters `{"alpha": 100, "C": 0.01}`.
- ETH-USD: `a83c2e8790df63e761269b632d201b75166fa59d1f793b5ec485a456aafc7e50`; parameters `{"depth": 3, "leaf": 25}`.
- SOL-USD: `ef02c2ccb088a8dd6ad7671b45bdae0974a0e526ddeae7859c8d4f1627b16233`; parameters `{"depth": 3, "leaf": 25}`.
- AAPL: `78c0a7b526010931c87843125461aaad6a57939f097505e41b58c4441e55a670`; parameters `{"depth": 5, "leaf": 40}`.
- MSFT: `a06c1a890a7a8435dd1ebe385c29650b2e0657c59262c4c6c6eb79937d14d653`; parameters `{"depth": 5, "leaf": 40}`.
- NVDA: `03ab02e6b76c331a576f2c0396457b1a88c9db326d4ecb787deb6badc9b4dfc9`; parameters `{"depth": 5, "leaf": 40}`.
