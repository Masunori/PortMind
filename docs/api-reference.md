# API reference

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Process health |
| `GET` | `/health/db` | Platform PostgreSQL health |
| `GET` | `/health/client` | Sanitized client identity and versions |
| `GET/POST` | `/api/sources` | Platform source management |
| `GET` | `/api/sources/scheduling/status` | Global automatic-collection status |
| `POST` | `/api/sources/{id}/collect` | Collect website evidence |
| `GET/POST` | `/api/evidence` | Evidence inbox and JSON ingestion |
| `POST` | `/api/evidence/upload` | Multipart upload directly to evidence |
| `PATCH/DELETE` | `/api/evidence/{id}` | Edit or delete unprotected evidence |
| `POST` | `/api/evidence/{id}/archive` | Archive evidence |
| `POST` | `/api/evidence/{id}/restore` | Restore evidence |
| `GET` | `/api/evidence/{id}/deletion-impact` | Preview audit and dependency protection |
| `GET` | `/api/evidence/{id}/duplicates/deletion-impact` | Preview batch cleanup of direct duplicates |
| `DELETE` | `/api/evidence/{id}/duplicates` | Delete unprotected direct duplicates and report protected skips |
| `DELETE` | `/api/evidence/{id}/raw-content` | Redact raw content while retaining metadata |
| `POST` | `/api/evidence/{id}/process` | Assess, interpret, ground, and map already-stored evidence |
| `GET` | `/api/evidence/{id}/processing-eligibility` | Explain retry eligibility and list prior signal attempts |
| `POST` | `/api/signals/{id}/review` | Human signal decision |
| `GET/POST` | `/api/scenarios` | Generic scenario definitions |
| `GET/POST` | `/api/plans` | Generic plan definitions |
| `POST` | `/api/plans/{id}/approve` | Approve a plan |
| `POST` | `/api/plans/{id}/reject` | Reject a plan |
| `POST` | `/api/experiments` | Freeze an immutable experiment |
| `POST` | `/api/experiments/{id}/submit` | Submit to the client |
| `GET` | `/api/experiments/{id}/results` | Poll and copy authoritative results |
| `GET` | `/api/settings/prompts` | List effective filter, interpreter, and planner prompts |
| `PUT` | `/api/settings/prompts/{agent}` | Store an operator prompt override |
| `DELETE` | `/api/settings/prompts/{agent}` | Restore the built-in prompt |

Operational model, document/candidate, local disruption, local simulation, ranking,
and legacy run endpoints have been removed.
# Planning cycles

- `POST /api/planning/cycles/entities/search` proxies a bounded, read-only search to the
  authoritative client registry and returns structured candidates for explicit scope selection.
- `POST /api/planning/cycles/hypotheses/generate` accepts a human prompt, a bounded
  structured entity scope, and a limit from one to ten. Each entity supplies its
  authoritative ID, type, display name, and optional bounded attributes. It returns strict `HYPOTHETICAL` proposals
  for browser-local review and does not persist signal records.
- `POST /api/planning/cycles` generates and persists validated risk scenarios without
  submitting a simulation. Body: `{"planning_starts_at": "2026-08-28T00:00:00Z",
  "planning_ends_at": "2026-09-27T00:00:00Z", "generation_limit": 5}`. The server
  loads eligible signal references. The request may also include `planner_mode`
  (`single` or `panel`), up to ten browser-confirmed hypotheses, and the same
  `entity_scope` used to generate them.
- `GET /api/planning/cycles` and `GET /api/planning/cycles/{cycle_id}` inspect snapshots.
- `POST /api/planning/cycles/{cycle_id}/scenario` selects one to 20 generated disruption
  IDs and freezes their reviewed composition.
- `POST /api/planning/cycles/{cycle_id}/baseline/submit` explicitly submits the reviewed
  scenario. If results are immediately available, AEGIS derives the allowed entity scope
  from the frozen scenario, passes the results unchanged to the selected planner, validates
  its interventions through the client, and returns the results and plans together.
- `POST /api/planning/cycles/{cycle_id}/baseline/refresh` refreshes a queued run and
  invokes the planner exactly once when authoritative results become available.
- `POST /api/planning/cycles/{cycle_id}/advance` is the first-party polling operation. It
  progresses baseline refresh, plan generation, every intervention simulation, and
  deterministic ranking, then stops at `RECOMMENDED` for human approval or rejection.
- `POST /api/planning/cycles/{cycle_id}/proposals` remains a compatibility endpoint for
  API callers that intentionally regenerate proposals with an explicit bounded scope;
  the first-party UI does not use it.
- `POST .../plans/{plan_id}/submit` and `/refresh` manage intervention runs for
  compatibility and recovery; the UI does not require them.
- `POST /api/planning/cycles/{cycle_id}/rank` applies `lexicographic-v1` for compatibility;
  normal cycle advancement ranks automatically.
- `POST .../plans/{plan_id}/reject` can reject a validated or evaluated proposal;
  `/approve` remains restricted to the deterministically ranked recommendation.

Provider-created numerical metrics and direct lifecycle promotion are not accepted by
any planning request schema.

Planning baseline and intervention runs are not experiment-package submissions. Their
run IDs and returned result dictionaries are retained in the `planning_cycles`
snapshot; `/api/experiments/{id}/results` and `simulation_result_copies` apply only to
the immutable reviewed-signal experiment workflow.

The connected client integration additionally exposes `POST /disruptions/reconcile`.
It classifies each complete-scenario item as `ALREADY_REFLECTED`,
`APPLY_IN_SIMULATION`, or `UNKNOWN`. Simulation requests carry both the complete
scenario for audit and only the active list for application.
