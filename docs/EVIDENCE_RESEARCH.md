# Document and options research

TraderX computes these measures in Python. AI Off leaves all of them available.
They describe collected evidence; predictive confidence remains zero until separate
out-of-sample validation. No extraction result authorizes an order.

## Earnings

Paste an authorized transcript in Earnings or fetch it explicitly from Alpha
Vantage. Include the asset and reporting-period end for earlier-period comparisons.
Speaker labels such as `Jane (CEO):` and `Alex (Analyst):` identify roles. Unknown
speakers remain unknown. The screen shows management/analyst Q&A pairs, numerical
guidance passages, keyword-based operational constraints, and differences from an
earlier distinct period already available to TraderX. Word overlap is a lexical
proxy; it does not establish evasiveness, deception or semantic contradiction.
Semantic work remains an optional task through the configured LLM policy.

## Insiders

Import actual Form 4 ownership XML, or configure the SEC document scheduler.
The issuer symbol can be read from nonempty transaction documents. The parser
retains owners, roles, footnotes, transaction codes, direct/indirect ownership,
derivative status and reported 10b5-1 indication. Missing prices remain missing.
Purchase/sale codes P/S include market **or private** transactions; they do not
prove personal-cash purchases or execution venue. Grants, exercises and derivative
transactions are excluded from purchase clusters.

The 3/7/14/30/60-day windows use transaction dates only after the filing becomes
available. Duplicate observations of a transaction do not inflate clusters.
An observed 4/A amendment blocks numerical insider inputs pending reconciliation;
it is never silently merged as a second purchase. Counts describe collected filings,
not a complete historical population. The independent evidence worker refreshes
rolling windows daily and recovers unfinished derivations every five minutes.

## Institutions

Import the 13F **information-table XML**, not the submission cover page. Supply a
consistent reporting manager CIK/identifier, quarter-end date, and confirmed value
units. Unknown units remain unknown; dollar totals are not guessed. Duplicate
allocation rows are combined by CUSIP, security class, option side and share/principal
unit. Calls, puts and common shares remain distinct. Individual filings show
reported weights, concentration and changes from an earlier available period.

Shared holdings compare only identified managers in the same selected period.
The displayed percentage is the share of **observed managers**, not ownership of
an issuer or free-float crowding. Missing manager/period metadata is excluded.
No CUSIP-to-ticker mapping is guessed. The latest snapshot per manager/period is
used: import amendments only when they are complete restatements, not additions.
Comprehensive amendment reconciliation and market-wide holdings coverage remain
outside the implemented scope.

## Historical options

The Options screen summarizes contract counts, complete-side put/call volume and
open-interest ratios, two-sided quote coverage, median relative spreads, nearby
50-delta implied volatility by expiry, and 25-delta put-minus-call IV. Delta matching
accepts a maximum absolute mismatch of 0.10 and retains the exact contracts used.
Missing, zero-denominator and crossed-quote comparisons remain unavailable.
Malformed rows are reported, mixed observation dates are rejected, and partial
chains produce no current numerical features. High volume/open interest is a
ranking, not evidence of buying, opening trades or informed intent. No dollar
notional or arbitrage is inferred without contract deliverables and synchronized
underlying/exercise/dividend/cost information.

## Availability, provenance and expiry

Raw documents, normalized events, analysis records, numerical features and signals
retain source IDs. A document identity includes text, source and interpretation
metadata. Successful LLM caching still uses content/model/prompt identity, so
metadata corrections do not require a repeat inference on unchanged text.
Publication and reporting-period dates remain separate from actual observation and
processing times. Future-publication documents wait before jobs or derived features
become eligible. Historical imports cannot backfill knowledge into earlier model
training observations.

Features expire: insider snapshots after one day, news after three, filing/transcript
measures after 120, and options at two calendar days after their observation date.
A stale historical option chain remains useful research but is not a current feature.
Explicit null features invalidate earlier values (including unresolved amendments
and missing Q&A measures). The as-of join honors both invalidation and expiry.

## Primary format references

Provider schema and failure behavior were tested with isolated fixtures. Credentialed
options/transcript access remains unverified until an entitled account is configured.
