# Risk, execution and security

The internal portfolio begins with explicitly simulated $100,000 cash and no
positions. The kill switch starts engaged. Resume affects only internal simulation.
STOP ALL TRADING blocks new fills immediately; it does not liquidate positions.

Risk requires a persisted TradeCandidate and checks expiry, future timestamps,
quote freshness, valid bid/ask, spread, price drift, positive net edge, supported
instrument, position/asset-class/gross exposure, cash, liquidity participation,
daily loss and peak drawdown. Shorting and unsupported derivatives are rejected.
Limits live in `config/risk.json`, not LLM prompts. Concurrent approvals are rechecked
against the current portfolio inside the fill transaction, preventing overspending.

Execution accepts exactly ApprovedOrder and requires a matching stored order and
positive risk assessment. Altering quantity or forging an ID fails. It rechecks risk,
provider health, expiry, kill switch and price at execution time. A durable fill ID
makes repeated submissions idempotent; a candidate can fill only once even if risk
approved it multiple times. Fees, slippage, cash and quantities update atomically.

The LLM schema cannot represent an executable order. It has no tools and no broker
credentials. Its output cannot invoke execution. User text and provider text are
untrusted; exact evidence quotes and output shape are validated before caching.

The backend is local single-user software. Host and Origin restrictions mitigate
cross-site requests; mutations require X-TraderX-Client: local-ui. These controls
are not Internet-facing authentication. Never expose the ports publicly as-is.
Credentials stay in the existing .env and secrets directories. API responses and UI
settings omit keys; transport errors use sanitized descriptions. Secrets, data,
models, caches, virtual environments and frontend build outputs are Git-ignored.

The repository checker scans candidate files and the existing Git index, including
known local secrets and secret patterns. It is a heuristic, not proof about remote
copies/history. No remote push or repository archive was created.

Still needed before broader execution: venue-specific paper/demo order adapters,
reconciliation, cancellations, pending-order reservations across external brokers,
sector/correlation/weekly-loss controls, stress scenarios, corporate actions and
full derivatives lifecycle accounting. Do not equate the current simulator with
those unimplemented broker capabilities.
