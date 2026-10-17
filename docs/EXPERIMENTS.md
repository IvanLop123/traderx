# Declared experiments

Research Lab and Experiments now support immutable ExperimentDefinition records.
Declare the hypothesis, signal, family, universe, threshold population, target,
horizon and costs before seeing the result. The API also accepts explicit period,
training/validation boundaries, prior-volume and known-regime filters.

The evaluator uses next-open entries and later closing targets, nonoverlapping
labels per asset, actual-observed evidence joins, and purged chronological
training/validation/holdout boundaries. Excess return uses the benchmark's same
entry-open / exit-close interval. Missing evidence is excluded, never inferred.
The default strict mode rejects newly downloaded history as historical evidence;
explicit retrospective mode relaxes market-bar observation only.

Training and validation results are returned first. Holdout rows are kept separately
and released only by an explicit action. Release is permanent and idempotent.
This prevents accidental viewing in the normal workflow; it is not cryptographic
access control against the local machine owner. A viewed holdout cannot become
fresh evidence by rerunning it. Records contain definitions and dataset hashes.

Diagnostics include rank correlation, returns/excess returns, realized volatility,
excursions, hit rates, cost sensitivity, per-asset/regime/year summaries,
499 within-asset circular-shift tests and moving-block bootstrap intervals. These
assume sufficiently stable dependence and do not establish causation or skill.
The event sleeve is descriptive, uses a 252-session annualization convention and
is not an executable cash-constrained portfolio. Use portfolio/event replay for
that. Capacity is an explicit 1% prior-volume assumption, not measured impact.

Every registered attempt remains counted, even if it fails or its holdout is
unreleased. Family BY correction assigns missing p-values 1 and includes repeated
trials. Do not evade the accounting by renaming families. Experiments outside
TraderX cannot be counted. No experiment automatically activates a strategy.

API: POST `/api/v1/research/experiments`, POST
`/api/v1/research/experiments/{definition_id}/holdout`, GET
`/api/v1/research/experiments/families`.
