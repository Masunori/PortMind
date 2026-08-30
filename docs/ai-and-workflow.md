# AI and workflow

Six purpose-specific protocols isolate probabilistic work: `FilterProvider`,
`InterpreterProvider`, `EffectMappingProvider`, `RelationshipProvider`, `RiskProvider`,
and `PlannerProvider`. Development uses transparent deterministic stubs; provider
selection is centralized in the integration factory.

`HypothesisProvider` is an additional review-only boundary. It turns a human planning
prompt into strict hypothetical signal proposals using Gemini structured output or a
deterministic stub. The server does not persist this output. The browser retains it in
`localStorage`, and only user-confirmed proposals enter scenario validation.

Hypothesis and risk providers receive a bounded `entity_scope`, not an unexplained list
of identifiers. Each entry contains a client-grounded `entity_id`, `entity_type`,
`display_name`, and optional non-sensitive attributes. Providers may target only entries
whose type is allowed by the selected disruption contract. Deterministic orchestration
rechecks membership and type compatibility; prompt wording is not the security boundary.

For accepted evidence, the deterministic workflow fetches the client's versioned
entity-resolution capability manifest before interpretation. The interpreter receives
it as untrusted reference data so extracted mentions are more likely to match
client-supported entity forms. It may not return trusted client identifiers;
authoritative grounding still occurs afterward through `ClientGateway.resolve_entity`.

## Gemini ingestion providers

The filtering and interpretation stages can independently use Gemini while the other
providers remain deterministic:

```dotenv
FILTER_PROVIDER=gemini
INTERPRETER_PROVIDER=gemini
GEMINI_API_KEY=replace-with-a-Google-AI-key
GEMINI_MODEL=gemini-flash-lite-latest
GEMINI_MAX_ATTEMPTS=3
GEMINI_TIMEOUT_SECONDS=30
```

`GeminiFilterProvider` and `GeminiInterpreterProvider` implement the same protocols as
their stub counterparts. They use Gemini structured output with Pydantic-generated JSON
Schemas. Each response is parsed and locally validated before it crosses the provider
boundary. Invalid JSON, missing or extra fields, out-of-range probabilities, and invalid
temporal windows cause a correction request. `GEMINI_MAX_ATTEMPTS` is the total number
of attempts, including the initial call; after the limit, `GeminiSchemaError` is raised.

Transport and API errors are not schema failures. Rate limits, timeouts, network
failures, and HTTP `500`, `502`, `503`, and `504` responses are retried with bounded
exponential backoff; a valid `Retry-After` delay takes precedence. Authentication and
other non-transient `4xx` responses fail immediately. Terminal errors expose only a
bounded provider message—never API keys, headers, prompts, or evidence content. HTTP
timeouts are bounded by `GEMINI_TIMEOUT_SECONDS`.

`GeminiHypothesisProvider` follows the same structured-output, retry, timeout, and
strict Pydantic validation path. Set `HYPOTHESIS_PROVIDER=gemini`; when omitted, Gemini
is selected if `GEMINI_API_KEY` is available and the deterministic stub is otherwise
used.

Before interpreting accepted evidence, AEGIS fetches both entity-resolution
capabilities and the versioned disruption catalog. The interpreter must return an
exact advertised disruption `type`; invented, translated, or reformatted types fail
local validation and trigger a bounded correction attempt. The same catalog snapshot
is then reused for effect mapping and client validation, so interpretation cannot race
against a different capability version.

The interpreter also returns every evidence-supported operational entity separately
from the subset directly targeted by the disruption. Both sets are grounded, but only
the target subset may populate a client disruption payload. This preserves upstream
and downstream context without applying the selected effect to unrelated entities.

## Stub planner panel

Each planning cycle freezes `planner_mode` as `single` or `panel`. Panel mode invokes
three deterministic role-labelled planners—continuity, cost, and resilience—through a
bounded coordinator implementing the existing `PlannerProvider` protocol. There is no
free-form conversation, configurable prompt, skill assignment, resource budget, or
external model call in this panel iteration. Every draft still requires client
validation and simulation before deterministic ranking and approval.

The LLM never supplies provider metadata or supporting evidence IDs. The adapter records
the configured model and Gemini response ID itself, and derives supporting evidence from
the input evidence (or none for a hypothetical). Entity output remains textual mentions;
authoritative IDs still come only from `ClientGateway` grounding.

The prompts explicitly treat evidence and client capability content as untrusted data. The filter is instructed
to quarantine prompt injection, but its output remains a proposal subject to the same
workflow boundaries and persisted review trail as the stub output.

The deterministic workflow owns thresholds, validation, persistence, review, and
version checks. Providers may suggest entity mentions and disruption payloads but may
not issue trusted identifiers. Entity resolution and business validation always go
through `ClientGateway`. Gateway failure produces an explicit failure and never
fabricated context, state, identifiers, or simulation results.

Human acceptance requires every mention to be authoritatively resolved and the
disruption to be normalized by the client. Experiments accept only immutable accepted
signal versions grounded against the current context.

The risk provider sees a bounded set of temporally eligible observed and forecast
signal references. It may select those immutable IDs and propose new hypothetical
payloads, but it cannot replace stored normalized disruptions or call the simulator.
Deterministic orchestration resolves selected IDs, validates hypothetical proposals,
enforces relationships, and asks the client to reconcile the complete scenario with
the frozen state before submitting only active disruptions.
