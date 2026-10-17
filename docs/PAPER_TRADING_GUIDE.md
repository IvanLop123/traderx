# TraderX paper-trading guide

Open `TraderX.command` in `/Users/ivanlopez/Desktop/traderx`, keep its window open, and visit **http://localhost:3000**. The launcher reuses healthy running services. Your Mac must remain awake for collection and simulated execution. Nothing runs while the computer or application is stopped.

## Your first paper trade

1. Use the search field at the top. Search a ticker or company, including `PLTR`, `AAPL`, or `BTC`.
2. Open its asset page. Review the dated price, liquidity, momentum score, experimental model forecast, uncertainty, and evidence warnings.
3. Select **BUY · PAPER**. Enter dollars or a share/coin quantity. Stocks and ETFs use whole shares; coins use up to eight decimal places.
4. Choose a market simulation or limit simulation. Review the bid/ask, timestamp, spread, adverse slippage, estimated fees, total, and available paper cash.
5. Click **Place Paper Order**. This records a local simulated order; it never sends an order to a brokerage or exchange.
6. Open **Portfolio** or **Orders**. After at least five seconds, fresh eligible quotes and displayed depth determine whether the order fills. Partial fills, no fills, and cash are normal outcomes.
7. Click a position to return to its asset page. **SELL · PAPER** pre-fills your held quantity. Review and confirm the exit. Short sales are not supported.

Market attempts expire after 60 seconds. Limit attempts expire after 24 hours, including weekends; they do not remain pending until the next business day. Cancel an open order's unfilled remainder in Orders. Confirmed fills remain in the ledger.

## Your account and watchlist

Your new personal paper account defaults to **$10,000**. It is created when you explicitly place your first order or confirm an account reset. It is separate from older internal research accounts and all model forward studies. Development and acceptance tests did not place orders in your account or reset it.

Settings → Personal paper account lets you choose a new starting balance. Reset requires the exact phrase **RESET MY PAPER ACCOUNT**. The previous account is archived and retained; its positions, orders, and performance leave the active personal view. Model studies are unaffected.

Stars save assets to your watchlist. Overview prioritizes your personal portfolio, momentum opportunities, warnings, watchlist, and recent orders. Scanner supports search, sorting, asset class, liquidity, known/unknown market cap, regime, strategy family, score, expected return, and probability filters. Missing values are not invented to satisfy filters.

## Reading the numbers

- **Momentum score:** percentile of trailing 20-session returns among currently research-eligible configured assets. It is not a probability or a buy recommendation.
- **Model forecast:** dated, experimental five-session expected return after estimated costs. The displayed model is selected using development data, not the holdout. No model qualifies for promotion.
- **Probability:** temporally calibrated probability of a positive return after the study's cost estimate. Calibration can drift. Residual uncertainty is an empirical error measure, not a guaranteed confidence interval.
- **Portfolio mark:** last observed bid; it can become stale. Cost is a clearly labeled fallback when no bid is available.
- **Day P&L:** change since the first observed valuation on the current UTC day. It is unavailable before that observation and is not a reconstructed exchange-close daily P&L.
- **Historical strategy returns:** research diagnostics from delayed daily-open return labels with conservative cost assumptions. They do not claim historical executable fills or arbitrary tradable size.

## Model studies

Portfolio → **Forward studies** is the scientific model evaluation area. It contains independent hypothetical books with fixed models, features, reasons, quotes, fills, and eventual outcomes. It never mixes your manual trades into model P&L or training. New books wait for a feature observation that becomes available after enrollment; historical predictions are not replayed as fresh evidence.

You can enroll a saved per-asset model or a pooled strategy with a matching asset class. The worker services up to 24 books per pass, rotating through enrolled books. Up to 500 books are supported by the configured operational bound; this is not a claim of institutional-scale load testing.

Completed observations stay quarantined. Releasing them requires retiring the cohort, waiting at least 90 days for every completed observation, and an explicit audited release request. Release creates a future-training manifest; it does not automatically retrain a model.

## Data and access

Your existing credentials were retained. No additional key is required to open the app, search, use the isolated simulator, or review collected research. Actual simulated fills require available real quotes:

- Crypto uses current Coinbase public bid/ask and displayed book size.
- Stocks/ETFs use the configured Alpaca quote feed and verified regular-session calendar. Historical SIP access does not imply a real-time SIP entitlement. Missing, stale, crossed, or unsupported quotes prevent fills. Stock trading outside regular sessions is not simulated.
- Small/unknown-cap stocks use stronger slippage and lower depth participation. Market capitalization remains unknown unless a legitimate dated source is supplied.
- Halts declared in instrument data or quotes block fills. A comprehensive live exchange halt feed is not integrated; fresh depth and session checks are additional safeguards, not a replacement for such a feed.
- Data Coverage and System health distinguish unavailable data from authentication success. Do not enable external trading flags to solve a data problem.

## Known execution limits

This is a conservative polling simulator, not an exchange queue simulator. It models spread, adverse slippage, fees, cash/share reservations, depth participation, delay, partial fills, expiry, and sessions. It does not model queue position, intrapoll prices, hidden liquidity, exchange-specific auctions, or guaranteed fills. It conservatively prevents reuse of the same quote across your simultaneous orders.

Verified splits and cash distributions have accounting support. Late splits overlapping newer fills, fractional entitlements, and unsupported corporate events pause the affected position for review rather than fabricating an adjustment. A complete operational corporate-action and halt feed remains a limitation for long-lived equity studies.