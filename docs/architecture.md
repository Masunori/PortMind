# Architecture

AEGIS is a platform around an authoritative, separately deployed operational client.
It owns evidence and review workflows, but it does not own the client's network,
shipments, inventory, entity registry, simulation rules, or calculated results.

There are two related execution paths:

```text
evidence -> provider assessment -> interpretation proposal
-> client-authoritative entity resolution -> client-normalized disruption
-> human signal review -> immutable experiment package
-> client simulation -> non-authoritative platform result copy

eligible accepted signals + confirmed browser hypotheses
-> risk scenarios -> client validation and state reconciliation
-> human scenario composition -> baseline client simulation
-> planner proposals -> client-validated interventions
-> intervention simulations -> deterministic ranking -> human decision
```

The second path is stored as a `planning_cycles` workflow snapshot. It does not create
an `experiment_packages` row for its baseline or plan simulations, and it does not use
`simulation_result_copies`. Instead, the cycle payload retains the frozen scenario,
client run IDs, returned result dictionaries, plan proposals, ranking, and decision.
Those retained results are non-authoritative copies; the connected client remains the
source of truth.

## Ownership boundary

The platform owns sources, collection records, evidence, assessments, immutable signal
versions, signal lifecycle and review state, relationships, generic scenario and plan
definitions, experiment packages, experiment result copies, planning-cycle snapshots,
and operator-configured provider prompts. The client owns operational entities and
state, stable identifiers, schemas, disruption and intervention contracts, capability
versions, execution, and authoritative results.

`HTTPClientGateway` is the only production adapter across the operational-client
boundary. Context-sensitive operations carry the applicable context, state, catalog,
schema, or capability versions. Run polling is keyed by the client run ID, and result
retrieval is associated with the frozen versions held by the experiment or planning
cycle. Tests inject `FakeClientGateway`; production cannot fall back to local
operational tables. Platform PostgreSQL contains no nodes, edges, shipments, aliases,
client schemas, simulation rules, client disruptions, or local simulation runs.

Provider calls, including Bedrock Converse calls, are separate untrusted external boundaries.
Provider selection is centralized in the integration factory. Providers cannot write
workflow records, call the simulator, promote lifecycle state, or manufacture trusted
client identifiers or metrics.

`integrations/model_provider.py` owns vendor-neutral output schemas, prompts, semantic
checks, and domain-contract conversion. Vendor adapters such as `bedrock.py` and
`gemini.py` own only transport, retry, structured-output mechanics, and provider
metadata; neither vendor adapter imports or inherits from the other.

## Signal and experiment path

Provider output contains textual mentions and proposals, never trusted client
identifiers. The interpreter may use the client's entity-resolution capability
manifest and disruption catalog as versioned extraction guidance, but both are treated
as untrusted data. Authoritative resolution and disruption normalization still occur
through `ClientGateway`.

Ambiguous or unresolved mentions block acceptance. Accepted mappings retain
their context, catalog, and schema versions; stale signals must be regrounded and
remapped before an experiment is created. An experiment freezes accepted signal
versions, normalized disruptions, context and state versions, provenance, probability,
and an idempotency key. Only completed experiment runs create rows in
`simulation_result_copies`.

## Planning path

Risk planning loads temporally eligible observed and forecast signal references from
the platform database. The risk provider selects among those immutable IDs and may
propose new hypothetical payloads. A separate `HypothesisProvider` can turn a human
prompt and explicit entity scope into browser-local hypothetical proposals. Those
proposals are not signal records; only hypotheses confirmed by the user are included
when a planning draft is created.

The client validates hypothetical disruptions and reconciles the complete scenario
with frozen operational state. Complete provenance remains in the planning snapshot.
Only disruptions marked `APPLY_IN_SIMULATION` become active simulator inputs;
`ALREADY_REFLECTED` items remain in the audit scenario, and `UNKNOWN` blocks
submission to avoid double counting.

Each cycle freezes one planner mode: a single `PlannerProvider`, the deterministic stub
panel when configured for stub panel mode, or the configured Bedrock planner for Bedrock
panel mode. `PlanningService` validates all provider output and coordinates the
`ClientGateway`. The client validates interventions, executes baseline and intervention
simulations, and calculates metrics. A deterministic `lexicographic-v1` policy ranks
completed plan results. Only an explicit API/UI action can approve or reject a plan;
approval records a decision and does not execute the intervention operationally.

Planning-cycle snapshots are platform-owned audit and workflow data. They contain
client version references, run IDs, and non-authoritative result dictionaries, never
operational model state. Domain contracts do not import providers or persistence
models; providers do not import database models or write records.

## Prompt configuration

Filter, interpreter, and planner Bedrock system prompts have safe built-in defaults and
may be overridden by an operator through `/api/settings/prompts`. Overrides are stored
in `agent_prompts` and are read when providers are constructed. They guide untrusted
model output but do not replace schema validation, client validation, version checks,
or human decision boundaries. Risk and hypothesis prompts are not currently
operator-configurable through this API.
