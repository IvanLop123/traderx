# Market structure research

Research → Market structure shows bounded intraday bars, observed quote/depth diagnostics, current options surfaces, signal decay, saved experiment comparisons and material recommendation history.

Stocks use dated exchange sessions; crypto uses 24/7 sessions. Missing intervals remain missing. Options use actual sourced indicative snapshots; quotes may be modified or delayed. IV/skew/Greeks/term structure/expected move are descriptive analytics, never executable parity or an options backtest. Unsupported historical IV rank/percentile is hidden.

Collection honors configured symbol, request, time-window and storage limits. Use the existing `scripts/research/market_structure.py` runner only for an explicit reproducible research run. Saved negative findings remain in MARKET_STRUCTURE_REPORT.md; no research result automatically promotes a strategy.
