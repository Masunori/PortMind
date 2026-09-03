# Client integration contract

This is the implementation checklist for an authoritative client connecting to AEGIS.
It documents the HTTP wire format used by `HTTPClientGateway`; these are not AEGIS's
browser-facing `/api/*` routes.

The client owns operational entities and state, capability schemas, simulation
execution, and authoritative results. AEGIS owns evidence, signals, reviews,
experiments, planning-cycle snapshots, and non-authoritative result copies. Dedicated
`simulation_result_copies` rows belong to immutable experiments; planning-cycle result
dictionaries are retained inside the cycle snapshot.

## Transport and errors

Configure a versioned base URL, for example:

```dotenv
CLIENT_GATEWAY_URL=https://client.example.com/integration/v1
```

All paths below are relative to that URL and exchange JSON. AEGIS sends
`Authorization: Bearer <token>` when configured and a unique `X-Correlation-ID` on
every request. Simulation submission also sends `Idempotency-Key`, equal to the key in
the request body.

| HTTP status | Meaning |
| --- | --- |
| `2xx` | Successful JSON response |
| `401`/`403` | Authentication or authorization failure |
| `409` | Context, state, or catalog version is stale |
| `429` | Rate limited and potentially retryable |
| `5xx` | Client unavailable; AEGIS may retry |

Other `4xx` responses reject the request. Errors must not expose secrets or sensitive
internals. Timestamps are ISO 8601, preferably UTC. Confidence values range from 0 to
1.

Payload schemas may use JSON Schema type arrays for nullable values, for example
`{"type": ["string", "null"], "format": "date-time"}` for an open-ended
`effective_until`. A required nullable property must still be present; remove it from
`required` when omission is also valid.

## Endpoint checklist

| Current workflow | Method | Path | Purpose |
| --- | --- | --- | --- |
| Required | `GET` | `/context` | Current identity and version stamps |
| Contract only | `GET` | `/schema` | Versioned client model schema |
| Planning | `POST` | `/entities/search` | Search authoritative entities for explicit planning scope and interventions |
| Required | `GET` | `/entity-resolution/capabilities` | Guide interpreter entity extraction |
| Required | `POST` | `/entities/resolve` | Ground mentions to authoritative IDs |
| Contract only | `POST` | `/state/query` | Read bounded authoritative state |
| Required | `GET` | `/disruption-contracts` | Advertise disruption payload schemas |
| Required | `POST` | `/disruptions/validate` | Validate and normalize a disruption |
| Required | `POST` | `/disruptions/reconcile` | Prevent double application in simulation |
| Required | `GET` | `/intervention-contracts` | Advertise intervention schemas |
| Required | `POST` | `/interventions/validate` | Validate and normalize an intervention |
| Required | `POST` | `/simulations` | Create an idempotent simulation run |
| Required | `GET` | `/simulations/{run_id}` | Poll run state |
| Required | `GET` | `/simulations/{run_id}/results` | Fetch authoritative results |

“Contract only” operations are declared by `ClientGateway` but are not currently
called by a production service. Implement them for complete gateway compatibility.

## Context and schema

### `GET /context`

```json
{
  "model_id": "client-a",
  "context_version": "context-v3",
  "schema_version": "schema-v2",
  "state_version": "state-2026-08-30",
  "capability_version": "capability-v5",
  "generated_at": "2026-08-30T10:00:00Z"
}
```

`context_version` identifies the entity/capability context used for grounding and
normalization. `state_version` identifies the simulation baseline. Return `409` when
supplied versions are no longer accepted.

### `GET /schema`

The response must contain `schema_version`; AEGIS retains the whole response as the
schema document.

```json
{"schema_version": "schema-v2", "entity_types": {}, "relationships": {}}
```

## Entities and state

### `GET /entity-resolution/capabilities`

This path returns machine-readable
guidance that helps the interpreter emit mentions the authoritative resolver can
understand.

```json
{
  "contract_version": "entity-resolution-v1",
  "entity_registry_version": "registry-v7",
  "entity_types": {
    "PORT": {
      "description": "A maritime port or terminal",
      "optional_hints": ["name", "country_code", "unlocode"]
    }
  },
  "resolution_statuses": ["RESOLVED", "AMBIGUOUS", "NOT_FOUND"],
  "examples": [{"mention": "Port of Singapore", "expected_type": "PORT"}]
}
```

The response must contain string `contract_version` and `entity_registry_version`
values and an `entity_types` object. AEGIS passes the complete manifest to the
interpreter as untrusted reference data, never executable prompt text. Do not include
system prompts, secrets, database details, or matching implementation instructions.
Actual grounding still occurs through `/entities/resolve`.

### `POST /entities/search`

```json
{
  "query": "Singapore",
  "entity_types": ["PORT"],
  "context_version": "context-v3",
  "limit": 10
}
```

```json
{
  "results": [
    {"id": "port-sg", "entity_type": "PORT", "name": "Port of Singapore"}
  ]
}
```

`query` is 1–300 characters and `limit` is 1–50.

### `POST /entities/resolve`

AEGIS currently sends one mention per request:

```json
{
  "mentions": [{"value": "Port of Singapore", "entity_type": "PORT"}],
  "context_version": "context-v3"
}
```

```json
{
  "results": [
    {
      "status": "RESOLVED",
      "candidates": [
        {"id": "port-sg", "entity_type": "PORT", "name": "Port of Singapore"}
      ]
    }
  ]
}
```

Allowed statuses are `RESOLVED`, `AMBIGUOUS`, `NOT_FOUND`, `UNSUPPORTED_TYPE`, and
`STALE_CONTEXT`. A resolved result must contain exactly one candidate. Ambiguous
results should include candidates. Entity IDs and types are authoritative client
references; resolution should be read-only.

### `POST /state/query`

```json
{
  "entity_ids": ["port-sg"],
  "fields": ["status", "capacity"],
  "context_version": "context-v3"
}
```

```json
{
  "state_version": "state-2026-08-30",
  "results": [{"entity_id": "port-sg", "status": "ACTIVE", "capacity": 100}]
}
```

Requests contain 1–100 entity IDs and 1–20 fields.

## Disruptions

### Generation entity scope

The platform gives hypothesis and risk providers only a bounded, frozen selection of
client-grounded entities:

```json
{
  "entity_scope": [
    {
      "entity_id": "port-sg",
      "entity_type": "PORT",
      "display_name": "Port of Singapore",
      "attributes": {"country": "SG"}
    }
  ]
}
```

The client remains authoritative for IDs and types. Attributes are optional and should
contain only non-sensitive values needed to distinguish or select entities. Assemble
the scope from authoritative resolution/search results and explicitly selected entities;
do not expose the complete registry by default. AEGIS rejects conflicting types for one
ID, out-of-scope targets, and targets that do not match the disruption's `target_types`.
The same scope accompanies confirmed browser hypotheses when a planning cycle is created.

### `GET /disruption-contracts`

Return each supported type with valid target entity types and a JSON Schema suitable
for local validation:

```json
{
  "catalog_version": "disruptions-v4",
  "disruption_types": [
    {
      "type": "PORT_CAPACITY_CHANGE",
      "valid_target_types": ["PORT"],
      "payload_schema": {
        "type": "object",
        "additionalProperties": false,
        "required": ["target_ids", "capacity_multiplier"],
        "properties": {
          "target_ids": {"type": "array", "items": {"type": "string"}},
          "capacity_multiplier": {"type": "number", "minimum": 0, "maximum": 1}
        }
      }
    }
  ]
}
```

AEGIS computes the SHA-256 hash of canonical JSON for each schema. Change the catalog
and capability versions when supported contracts change.

### `POST /disruptions/validate`

```json
{
  "context_version": "context-v3",
  "catalog_version": "disruptions-v4",
  "disruption": {
    "type": "PORT_CAPACITY_CHANGE",
    "payload": {"target_ids": ["port-sg"], "capacity_multiplier": 0.7}
  }
}
```

```json
{
  "valid": true,
  "errors": [],
  "normalized_disruption": {
    "type": "PORT_CAPACITY_CHANGE",
    "payload": {"target_ids": ["port-sg"], "capacity_multiplier": 0.7}
  }
}
```

Semantic invalidity should normally return `200` with `valid: false`, useful `errors`,
and no normalized value. Use `409` for stale versions. Validation is read-only: it
does not store, activate, or apply the disruption.

### `POST /disruptions/reconcile`

The client classifies each complete-scenario disruption against the frozen state:

```json
{
  "context_version": "context-v3",
  "state_version": "state-2026-08-30",
  "catalog_version": "disruptions-v4",
  "disruptions": [
    {
      "disruption_id": "signal-1-v1",
      "classification": "OBSERVED",
      "disruption_type": "PORT_CAPACITY_CHANGE",
      "normalized_payload": {"target_ids": ["port-sg"], "capacity_multiplier": 0.7},
      "source_signal_version_id": "signal-1-v1"
    }
  ]
}
```

```json
{
  "context_version": "context-v3",
  "state_version": "state-2026-08-30",
  "catalog_version": "disruptions-v4",
  "disruptions": [
    {
      "disruption_id": "signal-1-v1",
      "application_status": "ALREADY_REFLECTED",
      "normalized_disruption": {
        "type": "PORT_CAPACITY_CHANGE",
        "payload": {"target_ids": ["port-sg"], "capacity_multiplier": 0.7}
      },
      "reason_code": "PRESENT_IN_FROZEN_STATE"
    }
  ],
  "warnings": []
}
```

Status is `ALREADY_REFLECTED`, `APPLY_IN_SIMULATION`, or `UNKNOWN`. `UNKNOWN` stops
the workflow. Requests and responses contain 1–20 items.

## Interventions

### `GET /intervention-contracts`

This mirrors disruption discovery, using `intervention_types`:

```json
{
  "catalog_version": "interventions-v2",
  "intervention_types": [
    {
      "type": "EXPEDITE",
      "valid_target_types": ["SHIPMENT"],
      "payload_schema": {
        "type": "object",
        "additionalProperties": false,
        "required": ["target_ids"],
        "properties": {
          "target_ids": {
            "type": "array",
            "items": {"type": "string", "maxLength": 100},
            "minItems": 1,
            "maxItems": 100
          }
        }
      }
    }
  ]
}
```

### `POST /interventions/validate`

```json
{
  "context_version": "context-v3",
  "catalog_version": "interventions-v2",
  "intervention": {"type": "EXPEDITE", "payload": {"target_ids": ["shipment-42"]}}
}
```

```json
{
  "valid": true,
  "errors": [],
  "normalized_intervention": {
    "type": "EXPEDITE",
    "payload": {"target_ids": ["shipment-42"]}
  }
}
```

Invalidity and side-effect rules are the same as disruption validation.

## Simulations

### `POST /simulations`

```json
{
  "context_version": "context-v3",
  "state_version": "state-2026-08-30",
  "experiment_id": "scenario-42",
  "disruptions": [],
  "scenario_disruptions": [
    {
      "disruption_id": "signal-1-v1",
      "classification": "OBSERVED",
      "source_signal_version_id": "signal-1-v1",
      "application_status": "ALREADY_REFLECTED",
      "normalized_disruption": {
        "type": "PORT_CAPACITY_CHANGE",
        "payload": {"target_ids": ["port-sg"], "capacity_multiplier": 0.7}
      },
      "reason_code": "PRESENT_IN_FROZEN_STATE"
    }
  ],
  "interventions": [],
  "provenance": {"planning_cycle_id": "cycle-42", "kind": "baseline"},
  "idempotency_key": "experiment-42-baseline"
}
```

`scenario_disruptions` is the complete reviewed scenario retained for audit.
`disruptions` contains only items reconciliation marked `APPLY_IN_SIMULATION`, avoiding
double application of already-reflected conditions. `interventions` is empty for a
baseline and populated for plan evaluation. These two disruption arrays are intentionally
allowed together: they are not alternative representations. Every `scenario_disruptions`
item preserves the exact metadata returned by `/disruptions/reconcile`; `disruptions`
contains only the corresponding `normalized_disruption` values that the simulator applies.

```json
{"id": "run-123", "status": "QUEUED"}
```

Status is `QUEUED`, `RUNNING`, `COMPLETED`, or `FAILED`. Submission must be idempotent:
retries with the same key return the same logical run.

### `GET /simulations/{run_id}`

```json
{
  "id": "run-123",
  "status": "RUNNING",
  "updated_at": "2026-08-30T10:02:00Z",
  "error": null
}
```

For failure, return a sanitized `error` object with `code` and `message`.

### `GET /simulations/{run_id}/results`

```json
{
  "id": "run-123",
  "status": "COMPLETED",
  "results": {
    "late_shipments": 4,
    "average_delay_hours": 1.5,
    "total_cost": 125000
  }
}
```

The result object is client-defined and authoritative. AEGIS preserves it unchanged,
apart from reading the metric names used by its deterministic ranking policy and hard
constraints. If the run is incomplete,
return a non-`COMPLETED` status. Completed immutable experiments may create a dedicated
result-copy row; completed planning runs retain the dictionary in their planning-cycle
snapshot.

## Compatibility rules

- Never require AEGIS to manufacture client entity IDs.
- Prefer strict payload schemas with `additionalProperties: false`.
- Normalized values are the canonical forms later accepted by simulation, but
  validation itself has no side effects.
- Reject stale version combinations instead of silently translating them.
- Keep completed results retrievable by run ID; the client remains authoritative.
- Publish breaking HTTP contract changes under a new integration base path.

The executable wire-format source of truth is
`server/app/integrations/gateway.py`. Strict internal exchange models are in
`server/app/integrations/contracts.py`.
