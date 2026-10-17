# TraderX Decision Cockpit

Open `TraderX.command` in your Desktop/traderx folder. Keep its launch window open, then visit http://localhost:3000. It starts the local database dependencies, backend, collectors and production dashboard. Closing the launcher with Control-C stops the services it started. Data and credentials survive restarts. Avoid launching a second copy.

## Your everyday paper workflow

1. **Overview** shows the highest stored opportunity scores, their main evidence and risks, the daily decision board and high-risk candidates. A high relative rank can still say **No Trade**. Staying in cash is valid.
2. **Scanner** searches all 502 configured assets. Filter by class, known capitalization, liquidity, view, usable strategy family, regime or qualification. Scores, probability and uncertainty are different quantities. Unknown values are never treated as zero.
3. **View an asset** to see Bullish, Bearish, Mixed, No Trade or Insufficient Evidence. Read both the supporting and cautionary evidence. Strategy variants are collapsed; related families share dependence groups. Expand exact evidence for the stored feature values and model versions. The additional history/events section loads when opened.
4. **Paper Trade** opens a ticket; it never places an order by itself. Choose buy or sell, dollars or units, a shortcut amount, or a percentage of available cash. Sales require existing holdings. Stocks/ETFs use whole shares; crypto supports eight decimal places.
5. The optional **research size** is a conservative cap from volatility, uncertainty, liquidity, cash, pending orders and exposure. It is not forced and is unavailable when inputs are insufficient. Manual simulation still enforces cash, holdings and liquidity limits.
6. Add optional journal notes, whether you followed or disagreed with TraderX, and your expected outcome. **Review Paper Order** saves the research evidence and estimates spread, slippage, fees and allocation. **Place Paper Order** confirms the local simulation. Review again if the 60-second preview expires.
7. **Orders** shows delayed, partial, complete, canceled or unfilled attempts. A preview price is not a fill. Market attempts expire after 60 seconds, limits after 24 hours. Cancel the unfilled remainder of a limit order here. Fresh two-sided quotes, displayed depth, market hours and cash remain necessary.
8. **Portfolio** shows entry/current reference prices, P&L, entry/current research views, score and regime changes, and warnings. Sell, Trim and Add open another ticket. Changes in TraderX's view never automatically sell a manual position.
9. The **trade journal** records entry evidence, actual fills, realized trade P&L, holding time, observed favorable/adverse moves and view changes. Completed followed/disagreed groups are descriptive summaries, not evidence of predictive skill. Dividends remain in account totals; trade-journal P&L sums fill P&L. Between-poll extremes are unknown.

## Saved research and separate accounts

Use the star on an asset to build your **Watchlist**, then paper trade directly from it. **My Trade Ideas** stores notes and optional entry/exit/stop targets. These are tracking notes, not executable stop or limit instructions.

Your manual account, automatic **Model Paper Portfolio**, **Scientific Studies**, and **Historical Replay** remain separate. Manual notes and trades do not train models or contribute to scientific evaluation. Current automatic qualification count is zero; the automatic account remains in cash. Research can be experimental while still usable for a deliberate manual paper experiment.

## What you need to provide

Leave all broker/external execution switches disabled. The new tickets operate only on the local simulator. Do not paste keys into notes, chat, source files or GitHub. `.env`, secrets, local data, databases, logs and environment folders are ignored; run `.venv/bin/python -B scripts/api_setup/check_repository.py --history` from the repository.