# Signal catalog

All signals are exploratory; none has approved production predictive status.

| Feature / signal | Inputs and calculation | Interpretation / horizon | Limits |
|---|---|---|---|
| return_1/5/20/60/252 | Completed close-to-close bar returns | Directional evidence; matching bar horizon | Bar periods, not guaranteed trading days; revisions possible |
| return_20 signal | Sign and magnitude of 20-bar return | Bullish/bearish research evidence, 20 bars | Stored confidence is 0 until predictive validation |
| realized_volatility signal | 20-return sample SD, annualized | Volatility evidence | Current market UI uses daily crypto bars |
| volume_zscore / relative_volume | Rolling 20-bar volume moments | Participation evidence | Zero/insufficient variance yields missing values |
| VWAP / VWAP distance | Rolling typical-price × volume proxy | Price location | Bar proxy, not tick-exact exchange VWAP |
| ATR | Rolling true range | Volatility / risk context | No trade permission |
| RSI / MACD / Bollinger z | Conventional local calculations | Momentum / mean-reversion research inputs | Not privileged over other features |
| gap / intraday / drawdown / range | OHLC and historical peaks/ranges | Context | Equity calendar/corporate-action adjustments not certified |
| Form 4 transaction type/value | Deterministic XML transaction codes | Informational, filing availability onward | P code alone does not prove personal cash or forecast returns |
| 13F changes | Share differences by CUSIP | Delayed institutional evidence | Actual filing date required; quarter-end is not availability |
| Narrative numeric specificity / hedging | Regex counts and word denominators | Informational | Lexical proxies, not semantic evasiveness scores |
| Theme / bottleneck mentions | Keyword + constraint sentence matches | Evidence-backed text mentions | No inferred supplier links or fabricated severity |
| Social concentration / lexical disagreement | Author counts, keyword counts, engagement | Attention / disagreement research | Not semantic sentiment or a bot verdict |
| Trader PnL / expectancy / cost sensitivity | Authorized fills / CSV | Historical observed-trade analysis | Partial fills are not full account returns; no proven copyability |
| Option price / Greeks | European Black-Scholes | Derivative sensitivity | Constant parameters; American exercise caveat |
| Parity deviation | Bid/ask synthetic relationships less costs | Pricing evidence | Borrow, dividends and execution still require verification |
| Prediction probability | Explicit Beta-Binomial outcome assumptions | Informational probability interval | Requires justified exchangeability and evidence; no default fair price |

The feature store supports additional numeric evidence with availability timestamps.
LLM extractions retain provider, model, hashes, prompt version, quotes and uncertainty;
they do not automatically become calibrated directional signals.
