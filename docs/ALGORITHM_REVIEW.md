# Algorithm review — September 27, 2026

There is no universally best trading algorithm. TraderX should earn confidence
through comparisons against simple alternatives, chronological evaluation, explicit
costs and sufficient unseen evidence. The present models are research baselines.

## Primary research consulted

1. Hurst, Ooi and Pedersen, *A Century of Evidence on Trend-Following Investing*.
   The paper studies diversified trend following over long histories. It supports
   testing trend as a baseline; it does not validate this app's single-asset crypto
   implementation or its exact horizons.
   https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing
2. Bailey, Borwein, López de Prado and Zhu, *The Probability of Backtest Overfitting*.
   Repeated strategy selection can make attractive backtests misleading. TraderX
   retains trials and marks reused holdouts exploratory. An eight-block CSCV
   diagnostic now examines the four fixed development strategies (70 partitions);
   it does not account for undocumented trials or establish future performance.
   https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
3. Bailey and López de Prado, *The Deflated Sharpe Ratio*.
   Selection bias and non-normal returns matter. The app reports a probabilistic
   Sharpe diagnostic with caveats, not a deflated Sharpe or a certification of skill.
   https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
4. Scikit-learn's official time-series split and lagged-feature examples.
   Time ordering and separation between fitting and later evaluation motivate the
   chronological splits, training-only scalers and explicit gap/purge boundaries.
   https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
   https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html

## Changes made after review

- Compare cash, buy-and-hold, momentum, multi-horizon trend, volatility-targeted
  trend and mean-reversion with fixed rules. No automatic parameter search.
- Choose the research challenger using development performance only. Report the
  later holdout separately, including higher fee/spread/slippage assumptions.
- Add three expanding walk-forward folds with a purged label boundary. Every
  fold's labels end before the reserved holdout begins.
- Enforce next-open execution from earlier completed bars, long/cash constraints,
  turnover costs and terminal liquidation costs.
- Require return and probability forecasts to beat simple benchmark errors before
  generating a research candidate. Require at least 200 holdout observations.
- Retain NO_TRADE, separate risk approval and internal paper execution. No model
  or LLM can bypass approval or call an external order adapter directly.
- Download three years of available public daily spot history in bounded requests;
  distinguish retrospective history from actual first-observed replay.

## What the first live comparison showed

On the downloaded BTC history, the three development walk-forward Ridge forecast
folds had MSE approximately 0.000731, 0.000640 and 0.000381. Their corresponding
zero-return baselines were approximately 0.000714, 0.000637 and 0.000349. Ridge did
not beat that baseline in any fold. This argues against trusting that model's
apparent complexity. It is not a reason to tune repeatedly on the same holdout.

Results and their dataset/period evidence are saved in the local research database.
This observation is sample-specific, not a recommendation to trade another method.
The six strategy comparisons and forecast folds serve different purposes; the
forecast MSE result is not the return of a tradable forecast strategy.

## Limits that still matter

Corporate actions, delisted assets, historical universe membership, revised source
data, measured market impact, derivatives lifecycle, broad cross-market validation,
independent forward paper history require additional source access and accrued
observations. Declared-family trial accounting and explicit historical dataset
coverage gates are now implemented; they do not certify source completeness. Raw equity bars are explicitly unadjusted; stock
backtests crossing splits/dividends are unsuitable without the appropriate policy.
No current result establishes a durable or institutional-quality trading edge.

## Additional review and implemented checks

- Circular moving-block bootstrap (999 replicates, block length 10) reports a 95%
  interval for mean daily return and an approximate centered-null one-sided p-value.
  Weak stationarity and sufficient dependence capture are assumptions, not facts.
- Benjamini–Yekutieli adjustment covers the declared strategy family. It does not
  fix invalid p-values or repeated use of a holdout. Official implementation:
  https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html
- Ridge, a bounded random forest and histogram gradient boosting compete against
  a zero-return forecast using fixed settings and a chronological purged split.
  Automatic early stopping is disabled to avoid its internal temporal shuffle:
  https://sklearn.org/stable/auto_examples/ensemble/plot_hgbt_regression.html

The September 27 five-day BTC forecast comparison selected the zero-return baseline
on validation. Its validation/holdout MSE was approximately 0.002384/0.002684; none
of the three fitted challengers improved both. All four strategy mean-return
bootstrap intervals included zero, and within-family adjusted p-values were 1.0.
The development CSCV below-median fraction was 50%. This sample does not establish
a reliable edge. Records, periods and parameters are saved in the local database.

## Declared experiment follow-through

The September 28 review added immutable experiment definitions, separate holdout
release, per-asset nonoverlapping labels, source-availability joins, circular-shift
IC diagnostics and BY accounting that includes failed/unreleased/repeated attempts.
The first BTC/ETH/SOL five-day momentum experiment had validation rank correlation
approximately zero and mean cost-adjusted long event return of -1.44%. This does
not support promoting that signal. Its holdout release is recorded permanently.
These diagnostics do not resolve survivorship, data revisions or future regimes.

Primary sources rechecked: [time-series splitting](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html),
[backtest overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf),
and [trading-cost research](https://www.aqr.com/insights/research/working-paper/trading-costs).
