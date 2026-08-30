# Architecture

```text
source → evidence → provider assessment → interpretation proposal
→ client-authoritative entity resolution → client-normalized disruption
→ human review → immutable experiment → client simulation → normalized result copy
```

The platform owns sources, evidence, assessments, immutable signal versions, reviews,
relationships, scenarios, plans, experiments, and non-authoritative result copies. The
client owns operational entities and state, stable identifiers, schemas, disruption
contracts, capability versions, execution, and authoritative results.

`HTTPClientGateway` is the only runtime path across that boundary. Every exchange is
bounded and versioned. Tests inject `FakeClientGateway`; production cannot fall back to
local operational tables. Platform PostgreSQL contains no nodes, edges, shipments,
aliases, client schemas, simulation rules, client disruptions, or local simulation runs.

Provider output contains mentions and proposals, never trusted client identifiers. The
interpreter may use the client's entity-resolution capability manifest as versioned
extraction guidance, but the manifest is treated as untrusted data and does not replace
authoritative resolution.
Ambiguous or unresolved mentions block review. Accepted mappings retain their context,
catalog, and schema versions; stale signals must be regrounded before experiments are
created.

For risk planning, the platform loads temporally eligible observed and forecast signal
references from its own database. The risk provider selects among those immutable IDs
and may propose new hypothetical payloads. The client reconciles the resulting complete
scenario with the frozen operational state. Complete scenario provenance remains in
the platform; only disruptions marked `APPLY_IN_SIMULATION` are active simulator
inputs. An `UNKNOWN` reflection status blocks submission rather than risking double
counting.
# Planning trust boundary

Planning follows the same ports-and-adapters boundary as signal processing. One
`RiskProvider` is selected centrally, while each frozen cycle selects a single
`PlannerProvider` or bounded stub-panel coordinator. Provider output is
strict, qualitative, and untrusted. `PlanningService` alone coordinates validation and
the `ClientGateway`; the authoritative client alone validates capabilities, executes
simulations, and calculates metrics. A versioned deterministic policy ranks completed
results, and only a human can approve or reject the recommendation.

Planning workflow snapshots are platform-owned audit data. They contain immutable
client version references and non-authoritative result copies, never operational model
state. Domain contracts do not import providers or persistence models; providers do
not import database models or write records.
