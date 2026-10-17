# Alpha research and allocation completion report

October 15, 2026. Implemented directly in the existing TraderX repository. **Research/paper engineering is complete for this phase; profitable or independently qualified performance is not established.**

## Existing methods and additions

The [before-change audit](ALPHA_METHOD_AUDIT.md) records implementation and test evidence separately. Ridge/logistic, random forest, histogram gradient boosting, causal CNN/TCN, GRU, a small transformer, pooled cross-sectional ranks, meta-labeling, PCA, cointegration, Kalman, HMM, EWMA, GARCH, proxy neutralization, shrinkage, volatility targeting, risk parity and limited minimum-variance allocation already existed. They had real saved chronological experiments, although several lacked focused chronology tests or downstream portfolio comparisons.

Added: immutable alpha definitions/lifecycle; reserved forward evaluation and delayed adaptation lanes; bounded weight updates; six-reference, five-horizon decay; beta/proxy diagnostics; conditional pair-return scenarios; delayed regime/volatility sizing; seven fully constrained allocation proposals; shadow integration and reconciling attribution; and nine advanced dashboard views. Common-history covariance replaces zero-filled missing returns in this new allocator. Entry-only optimization cannot credit unexecuted sales. Restart/stale-governance checks block unsafe additions. Promotion tests run once at a frozen sample cutoff, not repeatedly until successful.

## Distinct hypotheses and evidence

Twelve registered hypotheses share **six conservative dependence groups**. Variants are grouped within their hypothesis, not counted as independent alphas. Nine have current fitted adapters; insider-event, crypto-funding and advanced-ML remain IDEA because this snapshot has no integrated forecast adapter. Historical diagnostics of a reference signal are explicitly distinct from exact fitted-model proof. The existing pairs-family single-asset adapter is a relative-value proxy; it is not a validated synchronized two-leg trading strategy.

Accepted research run: `alpha_research_dcaae12688b048e3e0ee5a8d0f2ae589bfa2695bac2f8bd06907bf829c88fda3`. Inputs/code/costs/seed and output hash are saved; the result cannot promote a strategy. Training labels end before 2022; comparisons cover already-inspected 2022–2024. No fresh historical holdout claim.

## IC, decay and correlation

Six reference hypotheses × five horizons = 30 comparisons. Nonoverlapping date counts at 1/2/5/10/20 sessions: **187 / 150 / 94 / 57 / 32**. Every Rank IC has BY-adjusted q = 1.0 under the 100-test reservation. Mean cost-adjusted active returns are negative at every measured horizon; some significant findings concern underperformance, not positive alpha.

| Reference | 1-session IC | 5-session IC | 20-session IC | 5-session mean active return | 5-session cost assumption |
|---|---:|---:|---:|---:|---:|
| momentum | -0.0129 | -0.0091 | 0.0209 | -0.78% | 1.04% |
| trend_following | -0.0033 | 0.0035 | -0.0082 | -0.91% | 1.04% |
| mean_reversion | 0.0125 | 0.0174 | -0.0291 | -0.82% | 1.03% |
| breakout | -0.0049 | -0.0101 | 0.0371 | -1.02% | 0.90% |
| relative_strength | -0.0135 | -0.0094 | 0.0198 | -0.77% | 1.04% |
| volatility | 0.0153 | -0.0091 | 0.0127 | -0.64% | 0.54% |

These compare top-decile net return against the same-date gross universe mean. Costs are source-panel assumptions, not calibrated executable spreads. Intraday alpha remains unvalidated. Registered fitted models retain their own five-session horizon; the diagnostic does not select a new winner or holding period.

Momentum/relative-strength active returns correlate **0.9990** over 94 aligned dates, showing redundancy. Momentum/trend correlation is 0.5808; reversal/low-volatility is −0.6429. Historical correlations are descriptive; forward exact-model dependence requires 40 mature paired dates. Runtime dependence groups prevent overlapping price hypotheses from becoming extra independent support.

## Factor findings

| Reference | Market loading of active returns | Momentum-proxy loading | Raw R² | Neutralized R² |
|---|---:|---:|---:|---:|
| momentum | 0.370 | 0.473 | 66.63% | 10.60% |
| trend_following | 0.185 | 0.266 | 22.31% | 19.11% |
| mean_reversion | 0.433 | -0.166 | 25.68% | 25.53% |
| breakout | -0.265 | 0.193 | 41.29% | 22.55% |
| relative_strength | 0.362 | 0.472 | 66.23% | 11.54% |
| volatility | -0.659 | 0.018 | 56.37% | 24.36% |

Conventional market/momentum proxies explain much of the observed variation. Neutralization does not establish novel profitable alpha. Historical size, value and dated sector attribution remain unavailable; no market-cap or sector-neutral claim is made.

## Relative value

| Predeclared pair | Training BY q | Training screen | Fixed scenario return | Kalman scenario return |
|---|---:|---|---:|---:|
| XOM / CVX | 0.54752 | Fail | -30.06% | 0.35% |
| KO / PEP | 0.27466 | Fail | -24.59% | 0.00% |
| V / MA | 0.11535 | Fail | -13.58% | -1.14% |
| GLD / IAU | 0.00074 | Pass | -30.82% | -0.19% |
| MSFT / AAPL | 0.73313 | Fail | -9.48% | 0.00% |

Only GLD/IAU passes the training screen; both its cost-adjusted scenarios lose. Failed-screen pairs are retained to expose negative results and are not eligible strategies. Borrow availability, synchronized quotes and legging risk are unverified. Zero Kalman return can mean cash/no triggered opportunity, not a successful strategy.

## Volatility and regime results

| Variance method | Squared-return MSE | QLIKE (lower is better) | Delayed sizing return | Maximum drawdown |
|---|---:|---:|---:|---:|
| realized | 5.1143e-08 | -8.1394 | 23.01% | 14.14% |
| ewma | 5.0352e-08 | -8.1961 | 22.68% | 13.95% |
| garch | 5.3960e-08 | -8.1521 | 17.13% | 15.30% |
| hmm | 5.8656e-08 | -8.1209 | 11.36% | 14.07% |

EWMA improves variance error slightly over the simple realized forecast but not sizing return. GARCH/HMM do not show a downstream advantage. These SPY scenarios reflect market exposure, not isolated alpha; fees are 10bp one-way turnover assumptions.

| Regime rule with identical realized-volatility sizing | Return | Drawdown | Dates |
|---|---:|---:|---:|
| always | 23.01% | 14.14% | 751 |
| deterministic_trend | 4.65% | 9.83% | 751 |
| hmm_expected_return | 3.02% | 11.92% | 751 |

The deterministic gate and HMM reduce exposure and drawdown but substantially reduce return. No corrected significance or independent improvement is established.

## Preserved deep-learning evidence

| Test year | Zero MSE | Ridge MSE | CNN/TCN MSE | GRU MSE | Transformer MSE |
|---|---:|---:|---:|---:|---:|
| 2022 | 0.0042863 | 0.0042465 | 0.0042845 | 0.0042349 | 0.0042801 |
| 2023 | 0.0026578 | 0.0026864 | 0.0026670 | 0.0026711 | 0.0026808 |
| 2024 | 0.0029239 | 0.0029227 | 0.0029345 | 0.0029230 | 0.0029241 |

GRU narrowly beats Ridge in 2022; several neural models beat Ridge but not zero in 2023; Ridge wins these comparisons in 2024. There is no consistent complexity advantage. Identical chronological fold rows and original artifacts are preserved.

## Portfolio construction

| Proposal | Net cumulative scenario return | Drawdown | Average exposure | Total cost drag* |
|---|---:|---:|---:|---:|
| equal | -3.92% | 9.01% | 10.30% | 10.13% |
| edge | -1.95% | 8.25% | 10.26% | 10.13% |
| inverse_volatility | -2.89% | 9.11% | 10.32% | 10.14% |
| volatility_target | 2.42% | 5.89% | 9.44% | 9.40% |
| risk_parity | -1.85% | 8.28% | 10.33% | 10.14% |
| confidence | -0.47% | 8.26% | 10.29% | 10.13% |
| mean_variance | 0.35% | 0.27% | 0.22% | 0.22% |

*Cost drag is the sum of interval costs as a fraction of contemporaneous sleeve capital, not a compounded dollar-account total. All methods use 94 nonoverlapping windows, the same baseline predictions and constraints. Volatility targeting scales its proposal before caps; inverse volatility retains the unscaled proposal with the same hard volatility ceiling. Differences are actual computations, not renamed results.

Volatility targeting is positive in this scenario but its mean-return interval includes zero. Mean variance is also slightly positive while holding about **99.78% cash on average**. Neither proves a superior forecasting model. All seven corrected return q-values are 1.0. The predeclared mean-variance shadow configuration was not selected from these results.

## Forward adaptation and execution

The prospective worker is running on 15 frozen symbols, at most eight per cycle. It records fresh features only after registration and waits for valid executable quotes. Evaluation symbols are never used to tune weights; adaptation observations mature seven days after completion. Minimum 60 independent dates, shrinkage, at least 80% prior influence and a two-percentage-point step bound prevent rapid performance chasing. Membership removal for safety is an explicit exception to ordinary normalization bounds.

**Adaptive versus fixed: insufficient evidence.** The paired equal-hypothesis/adaptive sleeve benchmark currently has zero completed independent dates and is not a full-account causal performance comparison. Hypotheses can be correlated. No historic winner or fictional test trade is substituted for forward evidence.

The shadow path now connects registered alpha forecasts, grouped ensemble, bounded adaptation, constrained allocation, deterministic risk, delayed quote fills, exits and attribution. Alpha/family/asset/regime/sector/sizing dimensions each reconcile to net P&L separately. Cash remains valid. The qualified Model Portfolio retains its independent model gate; the manual account and scientific studies remain isolated.

## Acceptance and current state



Final frontend result: **69/69 passed**. Production compilation/TypeScript/route generation passed; all nine research views were opened in the live browser, with final portfolio values verified and no console errors. The working-tree, Git-index and reachable-history credential scan and whitespace checks passed. The initial cold-start frontend run encountered timeouts; the final complete run passed after background allocation handling was improved and startup settled. Large refreshes can still take time; this is not a latency SLA.

Preservation: **687,059 original records and 1,334 historical files unchanged**, all credential hashes unchanged, no new manual orders/fills/resets/consents, and manual, shadow and qualified account trade/cash fields unchanged. Current primary daily bars: **1,281,018 across 501 archives**. Original deep/advanced/scientific results remain intact. Paid LLM calls: **0 before and after**.

Timestamped state: **8 HOLDOUT, 3 IDEA, 1 SUSPENDED, 0 qualified alphas**. Macro/regime is suspended because required data/features fail health checks; recovery requires three new healthy feature epochs. **36 superseded alpha versions** remain retired and retained. Separately, **27 model qualifications are FORWARD_TESTING** and none is qualified. Shadow: **zero orders, zero positions, zero completed portfolio trades; all cash**. The three prior statistical shadow observations remain preserved and are not relabeled as executed portfolio trades. All current implementation fingerprints match.

No external/live trading or paid inference was enabled. No Git push or credential changes were made. Existing methods/results, accounts and market-structure work remain intact.

## Remaining limits and use

Engineering completion cannot create elapsed forward market time. There is no qualified profitable strategy, no demonstrated adaptive advantage, no calibrated capacity estimate, no fundamental size/value/dated-sector test, no deployable pair-borrow model and no independently validated intraday alpha. Lifecycle definitions preserve missing metrics as unavailable. The bounded forward universe is intentionally smaller than the configurable research universe. Provider entitlement/outage states remain visible and can suspend dependent alphas.

See the [usage guide](ALPHA_RESEARCH_GUIDE.md) for startup and navigation and the [quantitative methodology](QUANT_RESEARCH_METHODS.md) for formulation, validation, execution and governance details. No additional API keys are needed for this phase.
