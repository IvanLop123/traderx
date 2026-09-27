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
   retains trials and marks reused holdouts exploratory; it does not claim to have
   implemented their complete CSCV/PBO procedure.
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
  or LLM receives a route to external orders.
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
full multiple-testing correction and independent forward paper history require
additional data and engineering. Raw equity bars are explicitly unadjusted; stock
backtests crossing splits/dividends are unsuitable without the appropriate policy.
No current result establishes a durable or institutional-quality trading edge.
