# Observed social history

X access remains explicitly disabled by default and requires the owner's paid-access
decision and bearer token. A fetch searches the most recent completed UTC hour,
allowing five minutes after its end. Defaults allow one page of ten posts;
`X_SEARCH_MAX_PAGES` (1–10) and `X_SEARCH_PAGE_SIZE` (10–100) bound provider usage.
No LLM is called. This search is explicit, not a continuously paid background feed.

A query window is complete only after pagination ends with no partial API errors,
missing identifiers/timestamps, duplicate pagination rows or out-of-window records.
Hitting the cap produces a truncated window, not an extrapolated total. All raw
observations retain query, window bounds, observation time and pagination coverage.

Complete windows support exact accessible-corpus mention counts and per-hour rates.
Acceleration needs the immediately preceding comparable window. A z-score requires
at least eight same-query, same-duration, nonoverlapping complete historical windows;
up to 28 are used. Re-fetching a window does not multiply evidence. Zero historical
variance yields unavailable, not division by zero. There is no seasonality correction.

Engagement velocity uses matching post IDs with repeated observed counters and an
actual elapsed interval. Missing counters/posts are not zero. Counter decreases are
reported as revisions and excluded. The result is summed increments/hour over the
matched sample, with its sample size shown. It is not total network virality.
Author concentration, duplicates and reposts are descriptive coordination proxies,
not bot/manipulation verdicts. None of these metrics establishes price direction.

Official endpoint contract:
https://docs.x.com/x-api/posts/search-recent-posts
