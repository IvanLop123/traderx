# Paper execution and reconciliation

## Internal simulator

Create a research candidate, evaluate its deterministic risk and explicitly execute
its stored approval in Orders. Cash, fees, positions and duplicate guards persist in
the database. Risk is rechecked at the actual assumed fill price. Internal fills do
not alter a broker account. Position exits also require fresh approval.

## Alpaca paper account

Set `ALPACA_API_KEY` and `ALPACA_API_SECRET` in the existing `.env` using paper-account
keys. Restart, open Portfolio or Orders, and refresh the broker account. Stock/ETF
quotes and history use the configured watchlist in `config/ingestion.json`.

Submission defaults to `ALPACA_PAPER_EXECUTION_ENABLED=false`. To use the adapter,
the owner must deliberately set it to `true`, restart, reconcile the account and
resume paper trading in Risk controls. Select Alpaca paper when assessing a candidate.
Only a persisted approval for that venue/account can reach the Submit button.
This documentation does not enable the flag. No broker order was sent during build.

Supported orders are whole-share US stock/ETF day limit orders, regular session only,
long/cash without margin borrowing. An approval expiry controls when submission may
start; the accepted broker order uses the stated day time-in-force. Use Cancel paper
order to request cancellation; partial fills remain authoritative and a request alone
is not confirmation. Crypto venues remain read-only/internal simulation.

The adapter pins `https://paper-api.alpaca.markets`; live endpoint configuration fails.
The broker supplies balances, positions, open orders and fills. Pending buys reserve
cash/exposure; pending sells reserve shares without freeing concentration capacity.
A separate broker ledger records account identity, approval, client ID and responses.
Paper broker state never overwrites the internal portfolio.

Before POST, a durable candidate reservation and deterministic client order ID are
committed. An uncertain outcome halts new orders and retains that reservation.
Subsequent attempts reconcile the same ID; they never repeat the POST or invent a
replacement. Unresolved submissions, account changes, unsupported positions, stale
snapshots or accounting mismatches prevent new submissions. A worker reconciles
configured enabled/pending accounts every 30 seconds, independently of AI.

There is no guarantee against account changes made by another client between snapshot
and submission. Broker rejection/partial-fill behavior remains authoritative. This
adapter has comprehensive mocked contract tests; authenticated operation awaits the
owner's account keys. It is not a production live-trading system.

Official contracts checked:
- https://docs.alpaca.markets/us/docs/working-with-orders
- https://docs.alpaca.markets/us/reference/postorder
- https://docs.alpaca.markets/us/reference/getallopenpositions
- https://docs.alpaca.markets/us/reference/getorderbyclientorderid

The implemented V2 order path accepts only saved `ApprovedOrder` values for that
account and venue. It supports whole YES contracts, explicit user probability
assumptions, immediate-or-cancel limits, primary subaccount, self-trade prevention
and reduce-only exits. No NO purchases, leverage or resting-order strategy exists.
There is a maximum $10 order reservation, $0.25 fee reserve per contract, one-percent
quoted-liquidity participation, and worst-case one-dollar-per-contract portfolio
concentration. These deliberately conservative demo limits may reject most markets.
Uncalibrated user probabilities are labeled assumptions, never trained forecasts.

A durable client ID and candidate reservation precede POST. V2 acknowledgments are
saved but canonical order details establish fills, partial cancellations and fees.
Any uncertain outcome halts new orders and is never resubmitted automatically.
Incomplete paginated account data, negative/unsupported positions, key changes,
stale/moved quotes, changed account snapshots, invalid tick increments and unresolved
orders all block submission. A background worker only reads/reconciles enabled or
pending demo accounts every 30 seconds. The separate demo account never overwrites
internal paper state. Changing keys while an order is unresolved requires returning
to its original account/key for reconciliation. Unexpected resting orders must be
resolved in the demo account before trading can resume.

No real demo order was sent during verification; signed HTTP contracts, partial
fills, duplicate retries, timeouts and risk failures were exercised with isolated
mock accounts and temporary keys. Actual authentication awaits the owner's key ID.