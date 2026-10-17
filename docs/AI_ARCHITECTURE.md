# Optional document extraction

Consumers use LLMService, TextTask and one LLMProvider interface. Disabled, local, OpenAI and hybrid implementations support off/local/openai/hybrid configuration. Routine quantitative work never enters this interface.

Allowed text tasks are transcripts, narrative filings, relevant news, contradictions, bottlenecks, themes, semantic disagreement and summaries. Structured filings and prices use deterministic parsers/calculations. Unchanged documents are cached permanently by SHA-256, task, provider/model, prompt version and system prompt. Relevant short documents can batch; failed possibly billed calls do not retry automatically.

Off mode returns DISABLED before any inference or provider health request. Local endpoints are loopback-only, without proxy inheritance or redirects; a blank local key adds no Authorization header. Hybrid defaults local, escalating only explicitly difficult allowlisted tasks that meet configured size, permission and budget gates. A failed local response never causes cloud fallback.

The persistent usage ledger reserves conservative maximum costs transactionally before cloud calls, then records calls, input/output tokens, estimated cost, module, provider/model and daily/monthly totals. Unpriced models are blocked. Default automation and escalation are off; $1/day, $15/month, 10 calls/hour. Budget exhaustion pauses text extraction, not market ingestion, risk, accounting, model research or simulation. Settings displays routing, usage and local model health.

Cloud access uses an API key with metered billing. Local inference requires a separately running compatible runtime. No sign-in/subscription integration or conversational UI is part of v1. The application has no OpenAI SDK dependency.
