# PSA ESG Platform

The local stack contains:

- Next.js client: <http://localhost:3000>
- FastAPI server: <http://localhost:8000>
- FastAPI documentation: <http://localhost:8000/docs>
- PostgreSQL: `localhost:5432`

The application currently provides a persisted supply-chain graph, deterministic shipment simulation, time-bounded network disruptions, downstream exposure analysis, weighted scenarios, and explicit contingency actions. The Next.js interface can compare every seeded intervention across every scenario.

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

The server applies pending Alembic migrations when its container starts. Waiting for health before seeding prevents the seed process from racing the migration process. The seed command is idempotent: it clears and recreates nodes, edges, shipments, disruptions, scenarios, and contingency plans.

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

## API

FastAPI exposes:

- `GET /health` — application process health
- `GET /health/db` — PostgreSQL connectivity
- `GET /api/network` — persisted nodes and edges
- `GET /api/shipments` — persisted shipments
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

`NEXT_PUBLIC_API_URL` is compiled into the production Next.js bundle. Set it to the browser-accessible API URL before building the client image.
