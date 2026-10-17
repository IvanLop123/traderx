# Research universe and forward studies

## Instruments and coverage

`config/research_universe.json` is the initial watchlist. System → Data coverage
can save a validated runtime override without rewriting application modules.
The contract allows 5,000 instruments, with bounded batches (24 by default, 50
maximum) and model fits (24 assets by default, 100 maximum). Do not backfill or
fit thousands of securities in one unbounded request. Configuring an instrument
does not fabricate its history or automatically start a large backfill.

Instrument identity, class, currency, exchange, known-at membership and inactive
status are separate from provider series. Current active **and inactive** Alpaca
listing snapshots are archived. They are not a historical constituent archive.
Current-watchlist studies are explicitly retrospective. A strict archived-membership
policy requires known-at timestamps and excludes an instrument before membership
was known or after known inactivity. Unknown inactive dates fail closed. Delisted
history can be retained under its stable instrument identity; trustworthy delisting
returns, old ticker mappings and point-in-time inclusion are still required for a
survivorship-free study. Today's active stock list cannot supply those facts.

Eligibility uses trailing **raw** price, share/base-unit volume, dollar volume,
minimum history and expected-session coverage. Current spread is a separate
execution gate. Unknown spread is unavailable, never zero. Default thresholds:
$5 price, 10,000 shares/day (100 base units/day for crypto), $1m daily dollar volume, 252 historical bars, 95% session
coverage, and 50 bps maximum execution spread. Thresholds are configurable; these
are research policy choices, not an assertion that every passing asset is tradable.
SIP volume is consolidated; IEX-only volume is not equivalent.

Immutable Parquet files under ignored `data/history/` are checksummed and addressed
by content. SQL manifests record provider, feed, adjustment and retrieval time.
Raw and all-adjusted stock vintages are separate. No raw update is appended to an
adjusted series. Daily archive refresh re-fetches the bounded configured equity
batch as one adjustment vintage; crypto adds a small overlapping raw window.
Unchanged content reuses its artifact. Older versions remain available. A changed
provider vintage cannot rewrite a frozen model's stored inputs or holdout outcome.

All-adjusted prices account for the provider's splits/dividends/spin-offs. They are
retrospective research prices, not historical executable quotes. Revisions and
current adjustment vintages are explicitly disclosed. Corporate-action events
are separately retained; provider processing dates do not prove announcement time.
The deterministic total-return utility handles split share conversion and cash
per post-split share; raw forward positions use explicit action events.

## Historical evidence

Form 4 indexing follows actual SEC submissions archive references and uses actual
acceptance timestamps. Transactions retain accession, source hash, issuer,
reporting owners, roles, code, shares, price, value and footnotes. Features cannot
appear before publication. A complete retrieved window plus a 60-day warmup is
required to infer zero purchase activity. Missing documents disable that window.
An unresolved amendment suppresses the following 60-day lookback. Original and
amended records remain immutable.

Purchase candidates require nonderivative code P acquisitions with dollar values.
Exercises, gifts, awards, explicit private placements and flagged planned purchases
are excluded. **P alone does not prove an open-market trade.** A separate confirmed
open-market count requires explicit footnote language. Counts, dollars, distinct
buyers, role-weighted counts, repeated buyers and days since filing are computed
locally. No fabricated historical 13F security mapping is added.

ALFRED output type 4 provides first-release observations. Chunked archive windows
avoid excessive vintage queries. Unavailable archive windows stay unavailable;
latest revised values are not substituted. Availability is conservatively delayed
to the next New York midnight after release, including DST. The ordinary updater
merges rather than truncating the archived first-release history.

## Cross-sectional research

The bounded comparison includes individual-symbol, stock/ETF class-pooled and
whole-US-universe pooled Ridge/logistic, random forest and gradient-boosting fits.
At each decision date, trailing eligible assets receive contemporaneous feature
ranks. Targets are five-session future relative return and probability of
outperforming that observed universe. Selection uses development dates; final
holdout release is explicit and immutable. Fits, validation and final holdout are
chronological with a horizon-plus-delay gap. Test timestamps are separated by seven
sessions. Counts show both asset rows and independent date clusters. Correlated
securities never count as thousands of independent temporal experiments.

Relative-return predictions alone do not authorize buying. Top-rank returns after
estimated costs are diagnostics. They do not establish executable performance,
statistical significance, or absolute positive expected return. Current-watchlist
membership and incomplete delisting returns block promotion. More advanced model
families can implement the same feature/prediction contracts later; no neural
network or reinforcement-learning training has been added.

## Forward paper ledger

Portfolio → Forward studies enrolls a frozen comparison. Each study receives a
separate hypothetical $100,000 book and a frozen policy. Maximum position 10%,
5 bps fees per side, 5 bps adverse slippage per side, at most 5% displayed depth,
5-second minimum latency, 30-second quote freshness and one-hour entry expiry are
defaults. These are assumptions, not calibrated venue guarantees.

Feature values, imputed fields, feature availability, model hash/version, dataset
version, prediction, target probability, residual uncertainty, regime, reason,
intended notional, entry delay and exit policy are saved before fills. Missing
current features force cash. Probability and net-edge failures have separate
reasons. The historical two-bar entry convention is preserved for enrolled models:
a complete additional bar/session is allowed before entry, followed by the minimum
latency rule. Entry expiry starts from the permitted entry time.

Quotes require actual two-sided prices, sizes, exchange timestamp, observed time
and verified base-unit size semantics. Buy at ask plus adverse slippage; sell at
bid less slippage; charge fees both ways. Whole equity shares are used. One quote
cannot repeatedly supply liquidity; out-of-order quotes are ignored. Size is
cash-constrained, displayed-depth-constrained and position-policy-constrained.
Excess spread or spread-consuming expected edge causes no fill. Partial fills,
expired unfilled entries and delayed exits are recorded. NY equity sessions use
provider calendars including holidays, DST and early closes. Unknown sessions
fail closed; crypto uses continuous sessions. There are no synthetic close/midpoint
fills. Exits wait for an eligible subsequent quote instead of inventing a price.

Known forward/reverse splits adjust held quantities. Cash dividends accrue as
receivables and become cash on their payable date. Unknown lifecycle events,
fractional split entitlements and missing action details pause fills for review;
mergers, spin-offs, cash-in-lieu and late-discovered actions require additional
reconciliation before those affected studies can be considered clean evidence.
The provider does not guarantee timely corporate-action publication. No simulation
can eliminate that source limitation. Independent books do not share displayed
liquidity as though they were one combined strategy.

Subsequent observed quotes, individual fills, fees, entry/exit costs, simulated P&L
and favorable/adverse excursions are append-only. Excursions describe observed
bid quotes only; intrapoll extrema are unknown. Cash decisions collect subsequent
price observations with zero simulated position/P&L. An observation with no entry
is explicitly unfilled, not a successful trade. The UI groups performance by model,
asset, feature family and regime; family attribution is descriptive, not causal.

Forward outcomes are **quarantined evaluation evidence**. No training pipeline
reads them automatically. A cohort must be retired with no pending position, all
completed trades must be at least 90 days old, and an explicit reason must be
submitted to the release endpoint. The immutable release manifest lists exact
outcome IDs and its release timestamp. Those samples are available only to a future
training cutoff after release. The cohort then loses untouched-evaluation status.
A training importer remains responsible for excluding released samples from its
validation/holdout. Time alone does not release observations.

## Provider documentation reviewed


## Expanded product phase