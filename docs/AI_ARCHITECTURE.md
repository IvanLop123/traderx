# Optional text AI

All consumers use `LLMService`, `TextTask` and the canonical `LLMProvider` contract.
The four implementations are DisabledLLMProvider, LocalLLMProvider,
OpenAILLMProvider and HybridLLMProvider. No application module imports the OpenAI
SDK. `requirements-app.txt` works without it. The original Phase 0 SDK is optional.

## Workload boundary

Permitted tasks: transcript, filing, news, contradiction, bottleneck, theme,
semantic_disagreement, summary and chat. Price ticks, OHLCV, indicators, PnL,
risk, accounting and options are not valid task types. Market polling and paper
execution have no LLM call path. Text inference runs in a separate worker task.
The chatbot receives only the message the user actually sends, not a background
portfolio feed. It has no tools or order interface.

In off mode analysis returns DISABLED before provider construction, health probes
or cache consumption. Local mode uses the configured loopback endpoint only,
with `trust_env=False` and no redirects. No Authorization header is added when the
local key is blank. Model-list health checks are explicit; they do not infer.

Hybrid routes to local unless the task is explicitly difficult, is on the routing
allowlist, meets the configured size threshold, escalation is enabled and an
escalation model is configured. Cloud policy, rate and budget gates still apply.
If escalation is ineligible for budget/configuration reasons, work stays local.
A local failure or unwanted answer never triggers OpenAI.

## Permanent cache and batching

SHA-256 cache identity covers exact document text, task, provider, configured model,
local endpoint, prompt revision and system-prompt hash. Source aliases do not
re-analyze identical content. Explicit changes to a model identifier/prompt revision
create a new analysis. There is no TTL. Back up the database to preserve the cache.

Compatible small text jobs are batched up to eight within the input cap. Each
source is claimed transactionally and retains its individual cache entry and
validated evidence quotes. The batch has one actual call/token/cost ledger entry;
child document entries count zero extra calls. Oversized or mixed work is processed
individually, never silently truncated. Oversized single documents are blocked;
users should explicitly split them into narrative sections.

News/theme/summary inputs first pass deterministic keyword filters. Other text
workloads must be explicitly submitted or ingested as relevant typed documents.
No social stream is sent automatically to an LLM. Output must match a Pydantic
schema; each quoted span must literally exist in its source document. Unsupported
quotes, truncated answers and malformed JSON are quarantined. Quoting validates
provenance, not factual truth or the correctness of the model's interpretation.

## Cost safety

Safe defaults:

| Setting | Default |
|---|---|
| LLM_PROVIDER | off |
| LLM_AUTOMATED_ANALYSIS_ENABLED | false |
| OPENAI_AUTOMATED_ANALYSIS_ENABLED | false |
| OPENAI_ESCALATION_ENABLED / legacy MODEL_ENABLED | false |
| OPENAI_DAILY_BUDGET_USD | 1.00 |
| OPENAI_MONTHLY_BUDGET_USD | 15.00 |
| OPENAI_MAX_CALLS_PER_HOUR | 10 |
| Maximum output tokens | 1200 |

Before sending, the database serializes cache claims and estimated-cost reservations
(SQLite BEGIN IMMEDIATE; PostgreSQL transaction advisory lock). Input bounds use
UTF-8 byte counts plus protocol overhead; output uses the enforced token ceiling.
Rates come from `config/llm_prices.json`. Only explicitly priced models can run in
OpenAI mode. Current routine nano rates were verified at $0.20 input / $1.25 output
per million tokens; update pricing deliberately when selecting another model.
Cached-token discounts are ignored, making estimates conservative.

Successful usage settles the reservation. Missing usage or ambiguous network errors
retain a conservative estimate. Automatic retries are prohibited for possibly billed
requests. Failed analysis is not treated as valid data. The ledger tracks actual
calls, input/output tokens, estimated cost, module totals and UTC daily/monthly
charges across restarts. All cloud calls, including chat, obey the budget and hourly
limits. A paused cloud call never stops market data, research or portfolio processing.

Estimates are not an OpenAI billing statement. Account-level spending limits should
also be configured independently. Local inference has no external API charge;
hardware/electricity costs are not estimated.

Settings safely persist provider, model and policy controls. Credentials are neither
returned to the browser nor written by the UI. Existing in-flight calls finish under
their old reservation after a setting change. Changing to Off prevents new requests;
it cannot undo a request already sent. The Settings API also supports prompt revision,
watch terms, routing task allowlist and size threshold. These advanced fields are
visible in the OpenAPI contract.

Official references checked September 25, 2026:
- https://developers.openai.com/api/docs/models/gpt-5.4-nano
- https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- https://lmstudio.ai/docs/developer/openai-compat


Non-secret environment defaults are fingerprinted. UI choices survive restarts
while those defaults are unchanged; an intentional environment routing/model/budget
change takes precedence on the next restart. A credential addition alone never turns
AI on. Local connection failures may be retried explicitly without discarding the
failed attempt ledger. Ambiguous cloud requests remain protected from retries.
