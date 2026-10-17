# News intelligence

TraderX collects Alpaca news using the existing Alpaca credentials. No additional paid provider, chatbot, remote classifier or LLM call is used. `ALPACA_NEWS_ENABLED=true` is the default; set it to `false` and restart to stop collection.

A dedicated collector runs continuously while the application is running, including premarket, after-hours and weekends. REST recovery polls once per minute in bounded pages; streaming receives new articles. A disconnected feed does not stop prices, research, portfolio accounting or paper execution. Keep the computer awake for continuous forward observation.

## Verified account access

On October 16, 2026 UTC, the existing account returned HTTP 200 from the news REST endpoint, authenticated to the real-time stream, and accepted the all-news subscription. No new stream story arrived in the 40-second observation window. Real-time **access** is verified; measured stream delivery latency is initially unknown. System displays the current connection, last successful poll, last received streamed story and observed publication-to-receipt age when available. An older latest headline is not proof of a delayed entitlement.

Source attribution is retained per article. Coverage is not exhaustive and is not represented as Bloomberg/Reuters equivalent. Publication age also includes editorial timing and article revisions; it is not a guaranteed network latency. A REST backlog is marked explicitly and recovered in bounded batches. A stopped app cannot collect news; recovery is not a completeness guarantee.

## Evidence and recommendations

- Filter to configured symbols or classified macro events before storing evidence. Crypto aliases are mapped explicitly. Macro stories without symbols remain context; ticker exposure is not invented.
- Preserve publication, revision, receipt and actual availability times. Availability is never backdated to publication. Store immutable revision receipts and a bounded recent working set.
- Deduplicate provider IDs, URLs and normalized same-day headlines. Revisions replace prior evidence in the working set. Near-duplicate stories that evade headline matching still cannot multiply predictive weight: the entire news family has zero predictive weight and one Boolean adverse-event guard.
- Classify earnings/results, guidance, M&A, analyst actions, management changes, financing, regulatory/legal, product/business and macro/industry events. Direction, materiality, novelty and uncertainty are explicit rules, not calibrated probabilities. Ambiguous/negated headlines abstain on direction.
- Refresh affected recommendations immediately on relevant new evidence. Save the exact news revision IDs and evidence with the decision. Material adverse news can block a new simulated entry; it cannot manufacture a return forecast or force an exit by itself. Protective risk rules continue separately.
- The news family is independent of the numeric model voting groups. Its predictive weight remains zero until a separately evaluated model has legitimate evidence. Positive headlines alone do not authorize entry. Staying in cash remains valid.
- Events expire from current decision context after 48 hours. They remain in the immutable research log. Forward-collected news is excluded from historical backtests and automatic training. No historical performance claim is made from this newly collected stream.

Overview shows important events; individual asset pages show mapped news; System shows access and delivery status. The recent working set is bounded to 500 relevant story clusters, with up to 50 returned per request. Historical receipts remain in the database.

Provider references: [Streaming real-time news](https://docs.alpaca.markets/us/docs/streaming-real-time-news), [Historical news](https://docs.alpaca.markets/us/docs/historical-news-data).
