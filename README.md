# PortMind Platform

The local stack contains:

- Next.js client: <http://localhost:3000>
- FastAPI server: <http://localhost:8000>
- FastAPI documentation: <http://localhost:8000/docs>
- PostgreSQL: `localhost:5432`

The application currently provides a persisted supply-chain graph, deterministic simulation, source and document ingestion, relevance review, grounded disruption candidates, validated scenario and plan generation, local LangGraph orchestration, observable background runs, deterministic ranking, and human plan decisions. Every AI-assisted path runs through the fixture-backed `AIProvider`; no AWS or model account is required.

## Prerequisites

Install Docker Engine (or Docker Desktop) with Docker Compose v2.

## Development

Build and start the development stack, waiting until its health checks pass:

```bash
docker compose -f compose.dev.yml up -d --build --wait
```

The client and server source directories are mounted into their containers. Next.js and Uvicorn reload when source files change.

Create or reconstruct the synthetic supply-chain data:

```bash
docker compose -f compose.dev.yml exec server python -m app.seed
```

The server applies pending Alembic migrations when its container starts. Waiting for health before seeding prevents the seed process from racing the migration process. The seed command is idempotent: it clears observable runs and recreates nodes, edges, shipments, disruptions, scenarios, and contingency plans.

To apply migrations explicitly:

```bash
docker compose -f compose.dev.yml exec server alembic upgrade head
```

Check the current migration revision:

```bash
docker compose -f compose.dev.yml exec server alembic current
```

Run the backend test suite inside the development container:

```bash
docker compose -f compose.dev.yml exec server pytest
```

For local development, install `server/requirements-dev.txt` in a virtual environment and run `pytest` from the `server` directory.

## Intelligence ingestion and operations review

This phase adds a provider-neutral path from external evidence into the existing deterministic MVP:

```text
Data source → Raw document → Relevance assessment → Intelligence event
            → Grounded candidate → Human confirmation → Disruption
            → Exposure/scenarios/plans/simulation/ranking
```

Open <http://localhost:3000/sources> for the analyst workspace and <http://localhost:3000/disruptions/candidates> for the operator inbox. Scraper mechanics remain in the Sources area; operators work with validated potential disruptions and their exposure previews.

All application actions provide consistent progress feedback. The active button displays an animated spinner and an action-specific label, exposes `aria-busy` to assistive technology, and cannot be submitted again until its request and interface refresh finish. Related controls are temporarily disabled to prevent conflicting operations.

### Sources and documents

Website sources have their own URL, enable state, HTML scraper configuration, interval, last run, next run, status, and error. **Collect now** performs an immediate HTTP collection. With `ENABLE_SOURCE_SCHEDULER=true` (enabled by `compose.dev.yml`), one APScheduler polling job checks every minute and runs only sources whose independent `next_run_at` is due. One source failure is recorded without preventing other due sources from running.

Expand **Edit source and discovery settings** on any configured website to modify the same fields available during creation: name, URL, description, collection interval, discovery mode, depth, page budget, keywords, RSS/Atom URL, sitemap URL, and allowed or excluded paths. Saving recalculates that source's next scheduled run from its new interval. **Delete** requires browser confirmation and permanently removes the source together with its collected documents and dependent review records through database cascades. Previously confirmed standalone disruptions are not deleted with their original evidence source.

Website collection can optionally discover article pages instead of storing only the configured landing page. The deterministic collector combines four mechanisms:

```text
configured website
├── advertised or explicit RSS/Atom feed ──→ terminal article URLs
├── explicit/default sitemap index ────────→ terminal article URLs
└── configured page ───────────────────────→ bounded same-site BFS
```

RSS and sitemap entries seed the shared URL queue directly and do not consume HTML link depth. HTML navigation uses breadth-first traversal. Depth `0` fetches only the configured page, depth `1` can fetch its accepted links, and depth `2` can traverse a news/category page to its articles. Article pages are terminal and are not expanded. The recommended starting values are depth `2` and a 50-page request budget.

Before enqueueing an HTML link, the collector applies same-host restrictions, allowed and excluded path prefixes, canonical URL normalization, tracking-parameter removal, `robots.txt`, and deterministic keyword/navigation scoring. URLs such as News, Press, Alerts, and Media hubs may be traversed even when they do not contain an operational keyword; unrelated leaf links are pruned. Fetched pages must match a configured keyword in their URL, title, or initial text before becoming raw documents. This is intentionally deterministic rather than LLM-controlled, so crawl coverage and tests remain repeatable. The existing mock-backed relevance assessment performs the later semantic classification.

To find a site's RSS or Atom feed:

1. Look for **RSS**, **Atom**, **Subscribe**, or the feed icon on its News or Press page.
2. Inspect the page source for `<link rel="alternate" type="application/rss+xml" ...>` or `application/atom+xml`. Auto mode detects these links.
3. Try common paths such as `/feed`, `/rss`, `/news/feed`, or `/atom.xml`.
4. Open the candidate URL directly. A feed normally shows XML containing `<rss>`, `<feed>`, `<item>`, or `<entry>`.
5. Paste that URL into the source's optional RSS/Atom field. Use **RSS/Atom only** when the feed is reliable; otherwise leave **Auto** selected.

Sitemaps are commonly advertised in `/robots.txt` or available at `/sitemap.xml`. A sitemap is useful for coverage but may contain non-news pages, so combine it with allowed paths and keywords. Discovery is bounded by depth `0–5` and a page budget of `1–500`; these limits apply independently to every configured source.

Uploads support UTF-8 TXT, PDF, and DOCX files up to 10 MB. Website HTML is reduced to visible text; scripts and styles are removed. Extracted text is whitespace-normalized and identified by SHA-256. Repeated content from the same source returns the existing document rather than creating a duplicate. The hash is a content identifier, not a security credential.

The relevant API surface is:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET/POST` | `/api/sources` | List or create sources |
| `GET/PATCH/DELETE` | `/api/sources/{id}` | Inspect, configure, enable, or remove a source |
| `POST` | `/api/sources/{id}/collect` | Run one website source immediately |
| `GET` | `/api/documents` | List normalized documents, optionally by `source_id` |
| `POST` | `/api/documents/upload` | Extract and store TXT/PDF/DOCX content |
| `POST` | `/api/documents/{id}/assess` | Assess relevance against the current network |
| `PATCH` | `/api/documents/{id}/assessment` | Apply or clear a human relevance override |

### Relevance and grounding boundary

The relevance service sends the provider a compact context built from persisted node names, transport edges, and active shipment routes. `MockAIProvider` supplies deterministic structured fixtures. Probabilities at or above `0.7` are `RELEVANT`, values at or below `0.3` are `IRRELEVANT`, and intermediate values are `NEEDS_REVIEW`. Human overrides change the effective decision without erasing the provider output or rationale.

Only effectively relevant documents can enter disruption extraction. Provider output contains human-readable locations, never trusted internal IDs. The backend resolves canonical node names and persisted aliases such as `Hai Phong`, `Port of Hai Phong`, and `VNHPH` to `hai-phong-port`. Unknown locations remain validation errors and cannot enter simulation state.

### Candidate lifecycle, events, and provenance

AI extraction writes only to `disruption_candidates`; it never writes directly to `disruptions`. Python validates disruption type, probability, severity, time ordering, document existence, grounded targets, and supported effect parameters. The lifecycle is:

```text
EXTRACTED → VALIDATED or INVALID → ACCEPTED or REJECTED
```

The Operations inbox shows confidence, probability, time window, deterministic downstream exposure, and every validation error. Operators can edit simulation-relevant values. Each edit stores the complete previous state in `candidate_versions` and re-runs grounding and validation. Only a `VALIDATED` candidate can be confirmed.

Reports with the same disruption type, at least one common grounded entity, and overlapping time windows share an `intelligence_event`; every supporting document remains linked through `event_documents`. Candidate provenance exposes source, document, effective assessment, grouped event, version count, confirmed disruption, and any attached orchestration run.

Candidate endpoints include:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/disruption-candidates/from-document/{document_id}` | Extract, ground, validate, and group evidence |
| `GET` | `/api/disruption-candidates` | List the operations inbox |
| `PATCH` | `/api/disruption-candidates/{id}` | Version and revalidate an edit |
| `POST` | `/api/disruption-candidates/{id}/reject` | Retain but reject evidence |
| `POST` | `/api/disruption-candidates/{id}/confirm` | Create a persisted deterministic disruption |
| `GET` | `/api/disruption-candidates/{id}/exposure` | Preview structural exposure before confirmation |
| `GET` | `/api/disruption-candidates/{id}/versions` | Inspect immutable edit history |
| `GET` | `/api/disruption-candidates/{id}/provenance` | Explain the evidence chain |
| `POST` | `/api/disruption-candidates/{id}/confirm-and-run` | Confirm and start the existing decision workflow |

The confirm-and-run path uses the existing observable run machinery. Progress is available through `GET /api/runs/{run_id}/events` as server-sent events, and generated plans still require explicit approval before execution. This repository deliberately stops at the mock provider boundary: it contains no real-model, Bedrock, AgentCore, or AWS-native ingestion adapter.

## Supply-chain workflow

After starting and seeding the stack, open <http://localhost:3000>. The graph is loaded from PostgreSQL through FastAPI.

The client uses an always-dark workspace. On desktop-sized screens, the supply-chain graph remains sticky in the left pane while alerts, simulation controls, scenario results, contingency comparisons, and ranking controls scroll in the right pane. On narrow screens the panes stack vertically so the controls remain readable.

The seeded route has two shipments and a deterministic baseline lead time of 42 hours. To compare scenarios in the interface:

1. Select **Run baseline simulation** and confirm the 42-hour result.
2. Inject the Hai Phong port-congestion disruption.
3. Run the simulation again and confirm the 78-hour result.
4. Disable the disruption and rerun the simulation to return to 42 hours.

While the congestion is active, the exposure warning reports two exposed shipments and one potentially affected customer. The graph highlights Hai Phong and its directly disrupted outbound route in red, then PSA Singapore, the warehouse, the customer, and connecting downstream routes in amber.

The disruption and its Active/Inactive state are persisted in PostgreSQL. Directly affected nodes and routes are highlighted in red, while all structurally exposed downstream components are highlighted in amber. The warning card reports exposed shipments and potentially affected customers. Toggling preserves the configuration for repeatable comparisons. Running the seed command removes the disruption and restores the baseline.

The seed also creates four manually weighted Hai Phong-to-PSA closure scenarios. Select **Run all scenarios** to execute them in one request. Results are calculated by the simulation engine against the 42-hour no-disruption baseline:

| Scenario | Probability | Cost | Delay | Lead time |
| --- | ---: | ---: | ---: | ---: |
| 24h closure | 45% | $4,640 | 20h | 62h |
| 48h closure | 35% | $4,640 | 44h | 86h |
| 72h closure | 15% | $4,640 | 68h | 110h |
| 120h closure | 5% | $4,640 | 116h | 158h |

Closures add waiting time but do not yet reroute shipments, so these scenarios have equal transport cost. Scenario disruptions are embedded in each scenario and do not change the enabled state of standalone disruptions.

### Contingency plans

The deterministic engine supports `WAIT`, `REROUTE_SHIPMENT`, `EXPEDITE_SHIPMENT`, and `USE_ALTERNATIVE_INVENTORY`. Actions can replace a shipment route or inventory origin and apply explicit transit-time and cost multipliers. The seed adds Ho Chi Minh and direct-air alternatives plus three plans:

- **Plan 1 — Wait:** leave both shipments on the disrupted Hai Phong route.
- **Plan 2 — Reroute:** send both shipments through Ho Chi Minh Port.
- **Plan 3 — Emergency air freight:** send both shipments directly from Supplier VN to PSA Singapore by air.

Select **Compare interventions** to run the Cartesian product of three plans and four scenarios in one request. Each cell displays cost, lead time, and delay against the 42-hour baseline. Current deterministic results are:

| Plan | Cost | Lead time across scenarios | Delay across scenarios |
| --- | ---: | --- | --- |
| Wait | $4,640 | 62h / 86h / 110h / 158h | 20h / 44h / 68h / 116h |
| Reroute | $5,740 | 38h / 38h / 38h / 38h | 0h / 0h / 0h / 0h |
| Emergency air freight | $18,540 | 10h / 10h / 10h / 10h | 0h / 0h / 0h / 0h |

### Deterministic ranking

Select **Rank plans** to aggregate the scenario matrix into expected values:

```text
expected cost  = Σ probability(s) × cost(s)
expected delay = Σ probability(s) × delay(s)
score          = w_c × expected cost
               + w_d × expected delay
               + w_r × worst-case cost
```

The weights are configurable in the client and through the ranking API. They must be non-negative, at least one must be positive, and the scenario probabilities must sum to 1. Lower scores rank first. With the default weights `cost=1`, `delay=100`, and `risk=0.25`, the results are:

| Rank | Plan | Expected cost | Expected delay | Worst-case cost | Score |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 ★ | Reroute | $5,740 | 0h | $5,740 | 7,175 |
| 2 | Wait | $4,640 | 40.4h | $4,640 | 9,840 |
| 3 | Emergency air freight | $18,540 | 0h | $18,540 | 23,175 |

Worst-case loss is currently represented by the maximum scenario cost. Costs do not vary between closure durations yet because interventions use fixed routes without congestion pricing. Changing to cost-only weights (`cost=1`, `delay=0`, `risk=0`) recommends Wait, demonstrating that ranking is driven entirely by the supplied objective configuration.

## AI provider boundary

AI-assisted iterations depend on the provider-neutral `AIProvider` protocol in `server/app/ai/base.py`. It exposes one asynchronous, generic method:

```python
await provider.structured_generate(prompt, OutputSchema)
```

`get_ai_provider()` is the dependency-injection boundary and currently returns `MockAIProvider`. The mock performs no network calls and has no cloud SDK dependency. It returns deterministic fixtures validated through the requested Pydantic output type, including this initial disruption extraction:

```json
{
  "event_type": "WEATHER_DISRUPTION",
  "location": "Hai Phong",
  "duration_min_hours": 48,
  "duration_max_hours": 72,
  "confidence": 0.8
}
```

Future provider adapters should implement `AIProvider` and be selected only through `get_ai_provider()`. Application services must not import a vendor adapter or SDK directly.

### Event interpreter

`server/app/agents/interpreter.py` converts validated `InterpretSignalRequest` text into an `InterpretedSignal` through `AIProvider.structured_generate()`. The interpreter itself has no knowledge of `MockAIProvider` or any future vendor implementation:

```text
signal text → EventInterpreter → AIProvider → InterpretedSignal
```

The mock recognizes the demo signal `Typhoon may disrupt Hai Phong for 2–3 days` and returns:

```json
{
  "event_type": "WEATHER_DISRUPTION",
  "locations": ["Hai Phong"],
  "expected_duration_min_hours": 48,
  "expected_duration_max_hours": 72,
  "severity": 0.7,
  "confidence": 0.8
}
```

Unrecognized signals return a deterministic `UNKNOWN` result with no inferred location, duration, or severity and zero confidence. This keeps local development predictable and prevents the mock from fabricating unsupported interpretations.

### Entity grounding

The interpreter produces human-readable locations only. `server/app/services/entity_resolution.py` owns the deterministic mapping from those names to persisted graph entities:

```text
"Hai Phong" → entity resolver → "hai-phong-port"
```

The repository's existing canonical ID is `hai-phong-port` (equivalent to the illustrative `PORT_HPH` identifier). Resolution is case-insensitive, punctuation-insensitive, and can match a location without a generic suffix such as “Port”. The service provides:

- `find_nodes_by_name()` — matched persisted node models.
- `find_edges_by_location()` — persisted inbound and outbound edges for matched nodes.
- `find_shipments_using_node()` — persisted shipments whose routes contain a grounded node ID.
- `ground_interpreted_signal()` — a complete `GroundedSignal` with verified node, edge, and shipment IDs plus unresolved names.

`EventInterpreter.interpret_and_ground()` composes the complete provider-to-domain flow. It never accepts graph IDs from AI output. For the Hai Phong demo it resolves `hai-phong-port`, edges `01-supplier-to-hai-phong` and `02-hai-phong-to-psa`, and both seeded shipments. Unknown locations remain in `unresolved_locations` and cannot enter simulation state.

### Validated scenario generation

`ScenarioGenerator` asks `AIProvider` only for assumptions: names, probability weights, duration, and severity. Python then rejects impossible values, requires grounded exposure, normalizes probability weights to exactly one, applies severity to supported disruption effects, and constructs domain `Scenario` objects. The deterministic mock proposes 24h, 48h, 72h, and 120h closure cases.

```text
AI generates assumptions
        ↓
Python validates assumptions
        ↓
Simulator computes consequences
```

### Capability-validated planning

`ContingencyPlanner` exposes read-only backend capabilities instead of trusting provider-supplied IDs:

- `get_affected_shipments()`
- `get_available_routes()`
- `get_inventory()`
- `get_transport_modes()`
- `get_route_capacity()`

Every proposed action is checked against grounded exposure, real directed routes, route bottleneck capacity, shipment eligibility, and available inventory before it becomes a domain `Plan`. The mock proposes Wait, Reroute via Ho Chi Minh City, Air-freight urgent inventory, and Partial air + sea. Invented nodes, missing legs, insufficient capacity, and unaffected shipments are rejected.

## Local LangGraph workflow

The provider-neutral workflow is compiled with LangGraph's `StateGraph` and works entirely locally:

```text
interpret signal
      ↓
ground entities
      ↓
analyze exposure ── no significant shipments ──→ END
      ↓
generate scenarios
      ↓
generate plans
      ↓
simulate plan × scenario matrix
      ↓
rank plans
      ↓
END
```

LangGraph receives `AIProvider`, so graph nodes do not care whether a future implementation is a mock, local model, or another provider. No LangChain model integration, LangSmith account, cloud deployment, or AWS dependency is used.

### Observable runs

`POST /api/runs` creates a persisted run with `GENERATED` status and schedules the local workflow as a FastAPI background task. `GET /api/runs/{id}` returns its latest state. `GET /api/runs/{id}/events` streams persisted server-sent events until the run reaches `COMPLETED` or `FAILED`:

```text
RUN_STARTED
SIGNAL_INTERPRETED
ENTITIES_GROUNDED
EXPOSURE_ANALYZED
SCENARIOS_GENERATED
PLANS_GENERATED
SIMULATION_STARTED
SIMULATION_COMPLETED × 16
RANKING_COMPLETED
RUN_COMPLETED
```

Event sequence numbers are monotonic and support cursor-based reads internally. Failed providers persist both `FAILED` run state and `RUN_FAILED` events instead of leaving work indefinitely active.

### Human decisions and canonical demo

Plans use `GENERATED`, `RECOMMENDED`, `APPROVED`, and `REJECTED` lifecycle states. Approval and rejection are explicit persisted API decisions; AI generation never approves an intervention.

The client includes **Reset Demo** and **Inject Demo Signal** controls. The canonical signal is:

```text
Severe weather may close Hai Phong for 2–3 days.
```

It reliably grounds Hai Phong, exposes both seeded shipments, generates four scenarios and four plans, executes 16 simulations, and recommends **Partial air + sea** using the workflow weights `cost=1`, `delay=300`, and `risk=0.25`. The UI consumes the SSE stream to show completed milestones and matrix progress, then allows the recommended plan to be approved or rejected.

Feature development intentionally stops here before any `bedrock.py` adapter. The repository contains no AWS SDK, Bedrock, or Bedrock AgentCore dependency.

## Extensible network model

The live digital twin can now be maintained at `/network/manage`. The responsive dark workspace has a topology overview with live counts, structured node and route cards, sticky creation panels, versioned schema summaries, and readable simulation-rule pipelines. Users can add and edit nodes and edges, preview dependency impact before deletion, create typed schemas, publish safe successor schema versions, and define deterministic metric rules. Graph changes are persisted immediately and are reflected by `GET /api/network`; seed data is no longer the only way to build the network.

Nodes and edges retain their stable core fields and may additionally reference an immutable `schema_version_id` with an `attributes` JSON object. Custom data is validated against that exact version. Supported field types are `NUMBER`, `INTEGER`, `BOOLEAN`, `STRING`, and `ENUM`; numeric fields can be classified as `STATIC`, `STATE`, `FLOW`, or `METRIC`. Custom fields cannot shadow core fields.

Schema definitions are never edited in place. A safe update creates `schema-id:v2`, migrates entities that referenced the prior current version, and fills newly introduced fields from declared defaults. A preview reports the entity count first. The first implementation permits additive fields, label changes, optional-to-required changes with defaults, and adding enum members. It rejects field removal, type changes, unit changes, behavior changes, and enum-member removal.

Simulation extensions are declarative rather than executable user code. A rule selects a supported lifecycle trigger, one of `SET`, `ADD`, `SUBTRACT`, `MULTIPLY`, `MIN`, or `MAX`, a validated numeric source, and a custom result metric. The current execution hook is `EDGE_TRAVERSED`; the domain vocabulary reserves later lifecycle hooks but rejects them until the engine implements them. For example:

```json
{
  "id": "accumulate-carbon",
  "name": "Accumulate route carbon",
  "trigger": "EDGE_TRAVERSED",
  "operation": "ADD",
  "source": "edge.attributes.carbon_emissions_kg",
  "target_metric": "total_carbon_emissions_kg",
  "enabled": true
}
```

Simulation responses expose accumulated values under `custom_metrics`. Disruptions may also apply the fixed numeric operation vocabulary to declared numeric fields such as `edge.attributes.carbon_emissions_kg`; persistence rejects invented fields, wrong entity kinds, nonnumeric fields, and missing affected targets. Plan ranking remains based on built-in cost, delay, and tail-risk metrics.

Every graph, schema, and rule mutation increments the persisted network context version. `services/ai_context.py` is the single source for compact filter context and detailed interpreter context, including authoritative IDs, routes, schemas, custom fields, and supported disruption effects. Large-context interpretation performs deterministic entity-name retrieval before constructing the prompt subset. This prevents either AI layer from inventing graph IDs or relying on stale independently assembled prompt context.

The baseline seed creates Supplier, Port, Warehouse, Customer, Truck Route, Sea Route, and Air Route schemas and associates every seeded node and edge with its corresponding version. To try the full custom-metric path, create a numeric `FLOW` field on an edge schema, publish the version, set values on matching edges, add an `EDGE_TRAVERSED` rule, and run the baseline simulation.

Automated coverage includes graph topology and dependency constraints, typed attribute validation, safe and unsafe schema changes, default migration, context invalidation and retrieval, rule source/trigger checks, every numeric operation, migration upgrade/downgrade, custom disruption validation, and an end-to-end carbon metric simulation. Run it with:

```bash
cd server
../.venv/bin/pytest -q
```

## API

FastAPI exposes:

- `GET /health` — application process health
- `GET /health/db` — PostgreSQL connectivity
- `GET /api/network` — persisted nodes and edges
- `GET /api/shipments` — persisted shipments
- `POST /api/nodes` — create a validated live-network node
- `PATCH /api/nodes/{id}` — edit a node without changing its ID
- `GET /api/nodes/{id}/delete-impact` — preview node dependencies
- `DELETE /api/nodes/{id}` — delete an unreferenced node
- `POST /api/edges` — create a validated directed edge
- `PATCH /api/edges/{id}` — edit edge topology or data
- `GET /api/edges/{id}/delete-impact` — preview edge dependencies
- `DELETE /api/edges/{id}` — delete an unused edge
- `GET /api/schemas` — list current node and edge schema versions
- `POST /api/schemas` — create a schema and immutable version one
- `POST /api/schemas/{id}/versions/preview` — validate and preview migration impact
- `POST /api/schemas/{id}/versions` — apply a safe successor version
- `GET /api/simulation-rules` — list declarative rules
- `POST /api/simulation-rules` — validate and create a rule
- `GET /api/network/context-version` — current canonical AI-context version
- `POST /api/simulations` — deterministic simulation using current disruptions
- `GET /api/disruptions` — persisted disruptions
- `POST /api/disruptions` — create or replace a disruption by ID
- `PATCH /api/disruptions/{id}` — enable or disable a disruption
- `GET /api/disruptions/{id}/exposure` — downstream structural exposure
- `GET /api/scenarios` — persisted weighted scenario definitions
- `POST /api/scenarios` — create or replace a scenario by ID
- `POST /api/scenarios/{id}/simulate` — simulate one scenario against baseline
- `POST /api/scenarios/simulate-all` — simulate all scenarios in one batch
- `GET /api/plans` — persisted contingency plans and typed actions
- `POST /api/plans` — create or replace a plan by ID
- `POST /api/plans/compare` — simulate every plan × scenario combination
- `POST /api/plans/rank` — rank plans with configurable cost, delay, and risk weights
- `POST /api/plans/{id}/approve` — persist human approval
- `POST /api/plans/{id}/reject` — persist human rejection
- `POST /api/runs` — create and schedule an observable local workflow
- `GET /api/runs/{id}` — retrieve current run state and final output
- `GET /api/runs/{id}/events` — stream persisted workflow progress over SSE
- `POST /api/demo/reset` — reconstruct the deterministic canonical demo

Interactive request and response documentation is available at <http://localhost:8000/docs>.

View logs:

```bash
docker compose -f compose.dev.yml logs -f
```

Stop the containers:

```bash
docker compose -f compose.dev.yml down
```

Stop the containers and delete development database and build volumes:

```bash
docker compose -f compose.dev.yml down --volumes
```

## Production-like environment

Update the password and other production settings in `.env.local` before starting the stack.

Build and start the production images:

```bash
docker compose --env-file .env.local -f compose.prod.yml up -d --build
```

Check container health and status:

```bash
docker compose --env-file .env.local -f compose.prod.yml ps
```

View production logs:

```bash
docker compose --env-file .env.local -f compose.prod.yml logs -f
```

Stop the production stack without deleting PostgreSQL data:

```bash
docker compose --env-file .env.local -f compose.prod.yml down
```

Production PostgreSQL data is held in the `postgres_prod_data` named volume. Do not add `--volumes` unless you intend to delete that database.

## Rebuild one service

For example, rebuild only the server:

```bash
docker compose -f compose.dev.yml up -d --build server
```

## Configuration

The server receives its database connection through `DATABASE_URL`. Within Docker Compose, services connect to PostgreSQL using the hostname `database`; `localhost:5432` is intended for tools running on the host.

`NEXT_PUBLIC_API_URL` is compiled into the production Next.js bundle. Set it to the browser-accessible API URL before building the client image. `CLIENT_ORIGIN` configures the exact browser origin allowed to call FastAPI and consume run events; production Compose requires it explicitly.
