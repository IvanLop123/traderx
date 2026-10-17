# Optional semantic research

The canonical text provider can return typed bottlenecks, public business
relationships, question/answer assessments and contradictory passages alongside
its existing summary. Exact source quotes are required and checked. Invalid
quotes or schema output are rejected; unknown attributes remain null. The
structured template changes the cache's prompt hash intentionally. Old successful
results remain in the ledger; they are never silently overwritten.

Bottlenecks retain company, type, severity, duration, affected product/revenue,
mitigation and quotation. Relationships preserve subject, relation, object and
source. Answers preserve question/answer topics, semantic similarity, directness,
specificity, skepticism, disagreement and follow-up judgments. Local code adds
lexical diagnostics and aggregates scores; a model does not calculate prices,
risk, accounting or indicators. Scores are subjective, not calibrated probabilities.

Earnings and Themes show source snapshots, relationship edges and conflicts.
Derived feature records retain provider, model, prompt version, document evidence,
actual processing availability and a 90-day expiry. Cached results produce no
duplicate features. Original snapshots preserve period comparisons for research.

## Cross-document changes

Earnings and Themes offer up to two related prior sources for each dated narrative.
Retrieval is deterministic: same asset, older publication, different content hash,
compatible named entity and minimum lexical overlap. Structured Form 4/13F data is
excluded. Undated sources cannot establish claim order; missing neighbors yield an
explicit unavailable result without inference.

A bounded prior/current pair is analyzed through the canonical `contradiction`
route. Quotes must belong to the correct document. Findings distinguish confirms,
updates, contradicts and a new claim relative to the compared source. There is no
claim of global semantic novelty. Each saved pair includes both source references,
processing availability, provider, model and prompt version. Oversized pairs are
blocked, not silently truncated. Permanent analysis caching prevents repeated
inference. Opt-in automation considers at most two eligible pairs per cycle; an
unchanged completed pair is revisited through the cache after a day, so deliberate
model/prompt changes can take effect. Disabled or paused AI does not block ingestion.
