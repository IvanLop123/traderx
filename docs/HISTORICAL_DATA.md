# Historical datasets and coverage

Public and credentialed feeds provide bounded history. TraderX does not claim a
complete institutional archive or reconstruct delisted universe membership from
current listings. Those are data entitlements, not facts an API key can manufacture.

Backtests → Historical datasets accepts an authorized `HistoricalDataset` JSON
object. The full schema is available in local `/docs` under POST
`/api/v1/research/datasets`. It includes:

- `name`, `source_reference`, and a precise `universe_definition`.
- `universe_includes_inactive`: explicitly declare whether the source includes
  inactive/delisted members for that universe. False blocks covered replay.
- `membership_known_at`: symbol → timezone-aware date when membership was known.
- `observation_policy`: `retrospective` (default) or `point_in_time`. Point-in-time
  mode rejects membership learned after its first eligible decision time.
- `corporate_actions`: source-attributed coverage intervals for each equity,
  each with `symbol`, `start`, `end`, `action_types` (`split`, `dividend`),
  `source_reference`, and `complete_for_window`. Both event types must cover the
  full replay window without gaps, even if the source declares zero events.
- `request`: the existing ReplayRequest contract: instruments, quote/lifecycle
  events, dated intents and execution/cost assumptions. Instrument intervals
  include inactive members; intents remain bounded by eligibility dates.

Imports are hashed and stored once. The coverage checker detects missing action
windows, unknown instruments, duplicate events and future membership. The UI stores
and exposes failed coverage reports but blocks replay until corrected source data
is imported as a new dataset. POST `/research/datasets/{id}/replay` revalidates the
stored declaration and runs the same cash/partial-fill/lifecycle engine.

Coverage declarations are checked for internal consistency, not independently
certified. Use unadjusted prices with explicit split/dividend events; never apply
splits twice to already adjusted prices. Lifecycle events must be available at
execution time. Research snapshots imported later stay labeled retrospective.
Physical short-option assignment and leveraged liquidation are unsupported.
The ordinary daily replay remains a bounded, user-selected baseline with explicit
survivorship warnings; it does not silently claim this stronger coverage policy.

No network, LLM inference or order submission occurs during dataset import/replay.
Keep source exports and licensed data outside Git; local databases and research
artifacts are ignored. Back up your local database separately.
