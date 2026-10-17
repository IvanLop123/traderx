# Event replay and market streaming

## Streaming

The public Coinbase WebSocket defaults on with heartbeat and five-second ticker
batches. It needs no key and never calls an LLM. REST polling continues independently.
System Health shows connection state, message count and update time.

Optional `.env` settings:

```env
COINBASE_STREAM_ENABLED=true
COINBASE_STREAM_BOOKS=false
COINBASE_STREAM_TRADES=false
```

Book mode reconstructs authenticated-free level2 batches from snapshots and absolute
size updates, removes zero levels and stores top-20 depth every five seconds. It is
sampled depth, not an exhaustive order-book event archive. Invalid/crossed state or
connection loss triggers a fresh snapshot. Full books have a bounded memory limit.
Trade mode detects ID/heartbeat gaps, attempts at most one bounded 100-trade recovery
per minute/asset and explicitly reports incomplete recovery. Recovered rows retain
actual arrival time. Sparse or recovered data must not be presented as complete tape.

A real public stream acceptance check received 185 messages, three quotes and three
sampled books in 15 seconds using an isolated database. Production defaults collect
quotes only. Actual rates vary.

Contracts: https://docs.cdp.coinbase.com/exchange/websocket-feed/overview and
https://docs.cdp.coinbase.com/exchange/websocket-feed/channels.

## Multi-asset research

Backtests and Strategies expose a portfolio replay using stored daily spot history.
The fixed 20-bar momentum baseline rebalances every five observations, targets at most
10% per asset/50% gross, waits for a later close and applies limit prices, a 1% volume
participation cap, fees, spread and slippage. Partial orders retain their remaining
quantity. This is a retrospective daily-snapshot approximation, not queue-level HFT
simulation. No strategy or model is automatically activated.

Strict observation mode excludes historical prices first obtained long after their
close. An empty eligible dataset gives an explicit error. Selected current assets
have survivorship bias. Raw equity history needs an explicit corporate-action review;
for actual splits/dividends use the event API and authoritative events.

`POST /api/v1/research/replay` accepts typed instruments, events and intents. The API
schema at `/docs` describes every field. All times require time zones. Instruments
carry multipliers, universe membership and contract terms. Quotes become usable only
when known; delayed packets cannot supply fresh historical liquidity. Intents cannot
use future evidence or fill on the quote that created them. Pending orders share each
event's volume cap. Long positions use full cash collateral, including perpetuals.

Supported explicit lifecycle events: equity split/dividend, perpetual funding,
position-specific borrow charges, binary payout resolution, cash-settled option expiry,
and physical call/put expiry when cash/shares cover delivery. Exercise events supply
the authoritative underlying settlement price. Missing settlement for an expired held
contract, duplicate IDs, future knowledge or late corporate actions fail the replay.
Early exercise, short option assignment and leveraged margin liquidation are not
implemented. The replay engine cannot submit real or paper broker orders.

Every run saves its complete typed input, content hash, decisions, partial fills,
lifecycle ledger, marked equity and assumptions. Open positions remain marked at the
end rather than being closed for free. Daily risk statistics use daily closing marks;
stress/liquidity assumptions are not measurements of actual execution quality.
