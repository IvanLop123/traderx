# Public-trader replication research

The Public Traders screen accepts authorized fill CSVs and public Hyperliquid
wallet reads. Descriptive metrics include trade PnL, concentration, asset breakdown,
rolling results, tail loss, size escalation and reported holding/leverage values.
Account Sharpe/Sortino/Calmar remain unavailable without cash-flow-adjusted equity;
closed-fill PnL does not provide an account return denominator.

The separate publication-delay replay accepts a `CopyReplayRequest` at
POST `/api/v1/traders/copy-replay`; its full schema is in http://localhost:8000/docs.
Paste the same JSON into the Public Traders replay panel. Required fields:

- `fills`: id, symbol, buy/sell side, quantity, original price, timezone-aware
  fill_at/public_at/ingested_at and source_reference. These times must be ordered.
- `market`: the Event Replay request: instrument definitions, authorized historical
  two-sided quotes/lifecycle events, costs, participation, cash and exposure limits.
  Its intents must be empty; public observations generate them.
- Optional analysis_seconds (default 1), expiry_seconds (300), limit_tolerance_bps
  (25) and original_realized_pnl.

Intent time equals ingestion plus analysis delay. Execution additionally waits the
market latency and a causally available valid quote. Limits are based on the
original observed price and declared tolerance, never a future price. The shared
replay ledger applies spread, fees, slippage, cash, participation, partial fills,
funding/borrow events when supplied, and instrument lifecycle rules. See EVENT_REPLAY.md.

A copyability score is reported only if original PnL is positive and the simulated
portfolio ends flat. It is capped replicated PnL / supplied original PnL. Compare
equal periods, sizing and cash flows. A timestamp without observation evidence is
a scenario assumption; downloaded wallet fills do not prove publication latency.
No historical quote tape is fabricated when none is available. This long/full-cash
research does not reproduce short or leveraged account strategies. No automatic
wallet copying or broker submission is performed.
