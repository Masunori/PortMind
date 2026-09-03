# Simulation and planning

Scenarios and plans are platform-owned, simulation-agnostic envelopes. Disruptions must
first be normalized by the client. Plan actions are opaque typed interventions with
client entity references and payloads; the platform does not interpret routes,
shipments, inventory, or other integration-specific ontology.

An experiment freezes context and state versions, signal versions, normalized
disruptions, provenance, probability, and an idempotency key. Submission
uses `POST /api/experiments/{id}/submit`; the client owns queued/running/completed/failed
lifecycle state and authoritative metrics. Failed or incomplete runs never create a
result copy. Completed copies preserve the exact experiment versions and client run ID.

Planning cycles use a separate persistence path. Baseline and intervention submissions
are sent directly from the frozen planning scenario and plan proposal; they do not
create experiment-package or simulation-result-copy rows. The `planning_cycles` payload
retains their run IDs and unchanged result dictionaries as non-authoritative workflow
copies.

Numerical examples are properties of the external demo client, not platform
calculations. The core platform stores undecomposed authoritative result dictionaries;
the planning workflow reads only the metric names used by its deterministic ranking
policy and configured hard constraints.

## Risk and planning workflow

The planning layer has one configured risk provider. Set `RISK_PROVIDER=stub` and
`PLANNER_PROVIDER=stub`; unknown values fail at provider construction. Each cycle
chooses either the single stub planner or the bounded deterministic role panel. Both
implement the same planner protocol and may return several alternatives.

The risk provider receives only bounded observed/forecast signal references that the
platform has already found temporally eligible. It returns selected immutable
signal-version IDs plus newly proposed hypothetical payloads. It cannot copy or replace
stored normalized payloads for existing signals, and it cannot submit simulations.

Entity selection is frozen as structured scope. Automatic generation uses the union of
entities grounded by eligible signals and entities explicitly selected for the cycle.
The explicit scope is carried from browser hypothesis generation into cycle creation,
so a client entity does not need an existing signal to appear in a confirmed
hypothetical. Conflicting types for one ID, IDs outside the scope, and targets whose
types are incompatible with a disruption contract are rejected before client validation.

Candidate signals are loaded from the platform signal database, not the browser. They
must be accepted, mapped, `READY_FOR_REVIEW`, observed or forecast, current for the
client context, and overlapping the requested planning horizon. The provider may
select a related subset, but deterministic code rejects unavailable IDs and rechecks
`REQUIRES`, `MUTUALLY_EXCLUSIVE`, and `SUPERSEDES` relationships. Existing normalized
payloads are fetched by immutable ID after selection.

Before submission, the client reconciles every selected or hypothetical disruption
against the frozen state. `ALREADY_REFLECTED` items remain in the complete scenario but
are excluded from active simulator inputs; `APPLY_IN_SIMULATION` items are applied;
`UNKNOWN` stops the workflow. This prevents observed effects from being counted twice
without assuming that the client's operational state includes them.

Provider contracts in `app.integrations.contracts` reject extra fields. Risk and plan
proposals are untrusted: their IDs, rationale, assumptions, and provider/model/prompt
metadata are provenance, not authoritative facts. In particular, `PlanProposal` has no
field for predicted metrics. Providers never submit runs, write workflow rows, rank
plans, or make human decisions.

The deterministic workflow is:

```text
client context + disruption contracts -> risk proposal -> client validation
-> frozen scenario -> baseline simulation -> completed client results
-> selected single/panel planner invocation -> client intervention validation
-> intervention simulations using the same scenario and versions
-> lexicographic-v1 ranking -> human approval or rejection
```

Risk generation is bounded to 20 proposals and 20 disruptions per proposal. The
service admits the client's restricted JSON schemas, validates payloads locally,
rejects unknown types and entity IDs, then requires client normalization. Frozen
scenario identity uses canonical JSON and includes context/state versions and
provenance. Empty provider responses are valid and produce no scenarios or plans.

The planner is called only after baseline status is `COMPLETED` and its authoritative
result has been retained in the planning-cycle snapshot. Intervention capability
discovery and validation use separate client endpoints; absence of those capabilities
is an explicit client error and never
causes disruption formats to be reused. Every intervention run carries the baseline
run ID and exactly the baseline's frozen disruptions, context version, and state
version. Refresh calls are safe: completed retained metrics are returned without another
result fetch.

`lexicographic-v1` minimizes, in order, `late_shipments`, `average_delay_hours`, and
`total_cost`; missing configured metrics sort as infinity. Hard-constraint violations
sort after feasible plans, and proposal ID is the stable tie-breaker. Failed and
incomplete runs stay in history but are excluded. Provider rationale and deterministic
ranking explanation are stored separately.

Lifecycle values are `PROPOSED`, `VALIDATED`, `SUBMITTED`, `RUNNING`, `EVALUATED`,
`FAILED`, `RECOMMENDED`, `APPROVED`, and `REJECTED`. Only a deterministically ranked
recommendation can cross the human decision boundary. Approval/rejection updates the
workflow snapshot; it does not mutate proposals, simulation inputs, or results.

## Planning API and failure behavior

Planning endpoints are under `/api/planning/cycles`: create/list/get a cycle, advance
the automatic workflow, and approve or reject. Granular baseline, proposal,
intervention, and ranking endpoints remain available for compatibility and recovery.
These are refreshable operations and do not hold requests open while a client run is
queued. `planning_cycles` stores platform-owned, non-authoritative
workflow snapshots and exact run/version links.

Provider timeouts, malformed output, and failures stop the current operation without
fabricating proposals. Client errors remain sanitized by the gateway. A stale context
or state stops the cycle; failed simulation errors may be retained only as sanitized
codes/messages. Reusing canonical inputs produces the same idempotency key.
Planning-provider API failures return sanitized `502` responses (`429` for quota
exhaustion) instead of unhandled server errors.

To add a real provider later, implement `RiskProvider`, `HypothesisProvider`, or
`PlannerProvider` and add an explicit factory branch. Providers receive only typed
requests. The stub panel is a bounded coordinator with three role-labelled drafts; it
does not implement voting, open conversation, dynamic membership, or partial-panel
recovery.

## Planning UI contract

The browser uses strict TypeScript lifecycle, scenario, proposal, evaluation, and
decision shapes in `client/types/planning.ts`. Pure presentation rules independently
gate baseline refresh, planner generation, plan submission, ranking, and human
decisions. The UI labels planner rationale as qualitative and renders numerical values
only from baseline or intervention results returned by the client. Unknown or non-numeric metrics are
shown as unavailable rather than coerced into a comparison.

### User workflow

Open **Planning** in the primary navigation. The overview reports client readiness and
the frozen context, state, and capability versions. The user chooses a planning
horizon; the server—not the browser—loads eligible stored signals and their grounded
entity references. Creating a cycle invokes the risk provider, validates and reconciles
every returned scenario through the client, and persists a `PROPOSED` review draft
without submitting a simulation. Before cycle creation, prompt-generated hypotheses
may be held under `AEGIS.planning.hypotheses.v1` in browser `localStorage`; they are not
written to the signal database. The user confirms or removes hypotheses, then confirms
or removes the compiled risk signals (up to the client contract limit of 20).
**Simulate** freezes that exact composition and submits its baseline.
Generated scenario alternatives are ordered by descending provider likelihood with
proposal ID as a deterministic tie-breaker. Impact values remain authoritative client
simulation results rather than provider predictions.

Queued baselines and intervention runs are polled automatically through the cycle-level
advance operation. Once the baseline completes, AEGIS persists a non-authoritative copy
of its result in the cycle snapshot, derives allowed target IDs from the frozen
scenario, and supplies the result unchanged to the cycle's selected single planner or
bounded deterministic stub panel. The same baseline response contains both results and client-validated plans; the
first-party UI has no separate plan-generation form or raw entity-ID input. Default or
cycle-frozen objectives and constraints are used for this invocation. The explicit
proposals endpoint remains only for API compatibility. Each returned alternative can be
simulated automatically and independently. When every plan run is terminal, AEGIS
applies deterministic ranking and stops at the recommendation for human approval.
Objectives and maximum metric/resource constraints entered at cycle creation are
frozen with the cycle, supplied to planners, and reused by deterministic ranking.
Completed results appear in a comparison
table with baseline deltas, constraint eligibility, rank, policy version, and separate
planner-rationale and deterministic-evaluation sections.

All returned plans are displayed as separate cards with provider provenance, validated
interventions, simulation controls, results, ranking explanations, and human
accept/reject controls.

Reject is available for validated and evaluated proposals. Approve appears only for a
`RECOMMENDED` plan after intervention simulation and deterministic ranking. The
confirmation states that this records a decision but does not execute an intervention. Failed cycles
remain readable and direct the user to correct operational state in the connected
system before starting a new frozen cycle.

### UI ownership boundary

The user controls risk generation, scenario review, the baseline simulation request,
plan evaluation, comparison, ranking, approval, and rejection from AEGIS. Planning
objectives and constraints are selected when the cycle is created, not re-entered after
simulation. The user directly controls
operational records, entity IDs, capability schemas, validation policy, simulator
rules, authoritative calculations, integration credentials, and execution of an
approved intervention in their connected system.

### UI verification

`npm test` covers lifecycle gating, deterministic ordering, missing and non-numeric
metrics, deltas, and status presentation. `npm run lint` checks client code, and
`tsc --noEmit` checks strict UI types. The planning route has loading and error
boundaries so read failures do not imply workflow state changed.
