# TraderX model paper portfolio

## Start and stop

Double-click `TraderX.command` in `/Users/ivanlopez/Desktop/traderx`, then open
http://localhost:3000. Keep the launch window open and the Mac awake. Closing the
app window alone does not necessarily stop the local services. Ctrl-C in the
launch window stops the services started by that launcher. Data remains in
`data/traderx.db` and the historical archives in `data/history/`.

The launcher rebuilds the UI after source changes. Do not launch multiple
independent copies against the same database. If a prior local server is still
running, the launcher reuses it; restart that prior server to load backend changes.

## Three separate books

- **Overview / Model Paper Portfolio:** TraderX evaluates candidates automatically.
  Passing candidates receive local simulated orders after evidence, sizing, risk
  and fresh-quote checks. This account has no broker connection.
- **Portfolio / My Manual Portfolio:** your own paper experiments, with a preview
  and explicit confirmation. These cannot change the automatic account.
- **Portfolio / Forward studies:** scientific observations from frozen models.
  These are quarantined evaluation data, not automatic training examples.

The model book starts at $10,000. It currently stays in cash because **zero models
have passed the new qualification gates**. This is not a missing-key error. More
API keys do not grant model eligibility or establish profitability.

## Daily use

1. Open **Overview** for model equity, exposure, opportunities and warnings.
2. Open **Scanner** to filter the 502-asset research universe. The score separates
   edge, costs, uncertainty, liquidity and other components. Asset details show
   family predictions and weights. Unapproved research is capped at 25/100.
3. Open **Models → Strategy families** (`/strategies`) for the source registry,
   validation, holdout and forward sample counts. Variants share dependence groups.
4. Open **Portfolio → Model Paper Portfolio** for automatic decisions, holdings,
   completed trades, costs and attribution. “NO_TRADE” is an evaluated cash choice.
5. Read **System** for provider status and the in-app model alerts on Overview.
   Optional feed entitlement failures remain visible; they are not treated as data.

The automatic worker checks saved state roughly every 30 seconds and refreshes
research rankings hourly. Quote requests for new entries are bounded. Polling can
miss intraday prices; it does not imply exchange-grade execution or 24-hour uptime.

“Pause automatic entries” prevents new entries and cancels pending buys on the
next processing cycle. Protective exits, accounting and unrelated collectors keep
running. Resume allows evaluation again; all evidence/risk gates still apply.

## Rules and configuration

Hard limits and the default exit/sizing policy live in
`config/model_portfolio.json`. Values are validated and have safety ceilings.
Policy changes invalidate an old opportunity snapshot until it is rebuilt. The
pause button persists a database policy override; while present, that override
takes precedence over the file. Advanced changes should use a validated policy
through the local Python interface and then restart; do not edit database JSON by
hand or remove qualification gates to make the account trade.

Defaults: 10% position, 30% sector, 60% asset class, 30% signal group, 25% correlated
cluster, 80% gross exposure, eight holdings, 10% drawdown stop, and 0.01% of average
daily dollar volume. At least two eligible dependence groups must vote, with a
score of 65, probability of 55% and positive estimated edge after costs. Missing
correlations are treated conservatively as fully correlated for risk.

Default sizing targets volatility with confidence/uncertainty discounts. Default
exit is five completed equity sessions or five elapsed crypto days. All policies
also request exits for portfolio drawdown, unreliable required inputs and maximum
holding duration. A stop requests a later fill; it does not guarantee a stop price.

## Keys, costs and model qualification

No new API keys or paid services are needed for this phase. Existing configured
feeds remain in use. The private `.env` and `secrets/` files were preserved; do not
send their contents in chat or commit them. See `docs/API_SETUP.md` for optional
provider setup and entitlement limits. An unavailable feed does not become usable
merely because an API key exists.

Qualification requires a new preregistered chronological evaluation, independent
forward observations, and a separate challenger portfolio comparison. Existing
already-inspected history cannot be renamed a fresh holdout. The registry freezes
criteria and saves blocked reviews; there is no UI “force promotion” control.
Research receipt adapters must supply the complete frozen, source-linked evidence
contract before eligibility can change. Merely waiting or entering keys cannot
promise an automatic promotion.

See `docs/MODEL_PORTFOLIO_REPORT.md` for exact acceptance results and limitations.
