# AI and workflow

Seven purpose-specific protocols isolate probabilistic work: `FilterProvider`,
`InterpreterProvider`, `EffectMappingProvider`, `RelationshipProvider`, `RiskProvider`,
`HypothesisProvider`, and `PlannerProvider`. Development uses transparent deterministic stubs; provider
selection is centralized in the integration factory.

`HypothesisProvider` is a review-only boundary. It turns a human planning
prompt into strict hypothetical signal proposals using Bedrock Converse structured output or a
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

## Bedrock providers

Filtering, interpretation, hypothesis generation, risk generation, and planning can
independently use Bedrock while effect mapping and relationship inference remain deterministic:

```dotenv
FILTER_PROVIDER=bedrock
INTERPRETER_PROVIDER=bedrock
HYPOTHESIS_PROVIDER=bedrock
RISK_PROVIDER=bedrock
PLANNER_PROVIDER=bedrock
BEDROCK_REGION=ap-southeast-1
BEDROCK_MODEL_ID=global.amazon.nova-2-lite-v1:0
BEDROCK_MAX_ATTEMPTS=3
BEDROCK_TIMEOUT_SECONDS=60
BEDROCK_MAX_TOKENS=4096
```

The Bedrock providers implement the same protocols as their stub counterparts. They use
Converse structured output with Pydantic-generated JSON
Schemas. Each response is parsed and locally validated before it crosses the provider
boundary. Invalid JSON, missing or extra fields, out-of-range probabilities, and invalid
temporal windows cause a correction request. `BEDROCK_MAX_ATTEMPTS` is the total number
of schema attempts, including the initial call; after the limit, `BedrockSchemaError` is raised.

Transport and API errors are not schema failures. Botocore applies bounded standard
retries to transient service and transport errors. Authentication, validation, and
other non-transient errors fail immediately. Terminal errors expose only a bounded
provider message—never credentials, request data, prompts, or evidence content. SDK
connection and read timeouts are bounded by `BEDROCK_TIMEOUT_SECONDS`.

`BedrockHypothesisProvider`, `BedrockRiskProvider`, and `BedrockPlannerProvider` follow
the same structured-output and strict Pydantic validation path. When
`HYPOTHESIS_PROVIDER` is omitted, Bedrock is selected if `BEDROCK_MODEL_ID` is configured;
otherwise the deterministic stub is used.

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
free-form conversation, per-role prompt configuration, skill assignment, resource budget, or
external model call in this panel iteration. Every draft still requires client
validation and simulation before deterministic ranking and approval.

## Operator prompt configuration

Bedrock filter, interpreter, and planner adapters read their system prompts when the
provider is constructed. Built-in safe defaults are used unless an operator stores an
override through `/api/settings/prompts`. Overrides are platform configuration in the
`agent_prompts` table; they do not change the strict response schemas or any
deterministic or client-authoritative validation boundary. The deterministic stub
providers do not use these prompts, and risk and hypothesis prompts are not currently
editable through this API.

The LLM never supplies provider metadata or supporting evidence IDs. The adapter records
the configured model and AWS request ID itself, and derives supporting evidence from
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
