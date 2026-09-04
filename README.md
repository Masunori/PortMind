# AEGIS Platform

AEGIS is a simulation-agnostic evidence, experiment, and risk-planning platform. It grounds signals against an authoritative client model, supports human review, hands immutable experiments to a separately deployed client, and coordinates client-executed baseline and intervention simulations in reviewable planning cycles.

The local stack provides:

- Next.js client: <http://localhost:3000>
- FastAPI server: <http://localhost:8000>
- Interactive API documentation: <http://localhost:8000/docs>
- PostgreSQL: `localhost:5432`

Every AI-assisted path uses deterministic stub providers by default. Local development requires no model account, API key, or cloud service.
The ingestion, hypothesis, risk, and planning providers can use Amazon Bedrock
Converse structured output; see
[AI and workflow](docs/ai-and-workflow.md) and [operations](docs/operations.md) for the
provider boundaries, retry behavior, and configuration.

## Backend tests

Run the complete Python suite, including the shared DynamoDB Local contracts:

```bash
scripts/test-backend.sh
```

Install the tracked pre-push hook once to run that suite before every push:

```bash
scripts/install-git-hooks.sh
```

GitHub Actions also runs the same script on every push and pull request.

## Quick start
Prerequisite:
- Docker Engine or Docker Desktop with Docker Compose v2.
- Run the demo client, make sure it is listening to port 8100.

In the `/server`, create an `.env.local` file:
```
POSTGRES_DB=psa
POSTGRES_USER=psa
POSTGRES_PASSWORD=replace-with-a-strong-password
PERSISTENCE_BACKEND=postgres
NEXT_PUBLIC_API_URL=http://localhost:8000

CLIENT_GATEWAY=http
CLIENT_GATEWAY_URL=http://host.docker.internal:8100/integration/v1
CLIENT_GATEWAY_TOKEN=demo-client-token

BEDROCK_REGION=ap-southeast-1
BEDROCK_MODEL_ID=global.amazon.nova-2-lite-v1:0
BEDROCK_MAX_ATTEMPTS=3
BEDROCK_SDK_MAX_ATTEMPTS=2
BEDROCK_TIMEOUT_SECONDS=60
BEDROCK_MAX_TOKENS=4096

FILTER_PROVIDER=bedrock
INTERPRETER_PROVIDER=bedrock
HYPOTHESIS_PROVIDER=bedrock
RISK_PROVIDER=bedrock
PLANNER_PROVIDER=bedrock

# Automatic collection requires both this global switch and a scraper whose
# "Schedule automatic collection" option is enabled. It defaults off.
ENABLE_SOURCE_SCHEDULER=false

```


```bash
docker compose --env-file .env.local -f compose.dev.yml up -d --build --wait
docker compose --env-file .env.local -f compose.dev.yml exec server python -m app.seed
```

Then open <http://localhost:3000>. The active workspaces are `/evidence` and `/sources`; the home page reports the authoritative client connection and version tuple.

Run the backend tests with:

```bash
docker compose -f compose.dev.yml exec server pytest
```

## System overview

```text
evidence → relevance filtering → signal interpretation
→ authoritative entity grounding → disruption mapping and validation
→ human review → immutable experiment → client simulation

eligible signals + confirmed hypotheses → reconciled scenario draft
→ human composition → baseline simulation → plan simulations
→ deterministic ranking → human decision
```

The platform owns evidence, assessments, signals, reviews, scenarios, experiments, planning snapshots, operator prompt overrides, and non-authoritative result copies. The client integration owns operational data, entity identifiers, model state, capability contracts, simulation logic, and authoritative results. Experiment results use dedicated copy rows; planning results remain inside the planning-cycle snapshot.

## Documentation

Start with the [documentation index](docs/README.md), or jump directly to:

- [Getting started](docs/getting-started.md) — setup, migrations, tests, and code-reading path
- [Architecture](docs/architecture.md) — ownership, gateways, providers, validation, and persistence
- [Ingestion and review](docs/ingestion-and-review.md) — sources, evidence, filtering, grounding, and lifecycle
- [Simulation and planning](docs/simulation-and-planning.md) — scenarios, contingency plans, ranking, and experiments
- [AI and workflow](docs/ai-and-workflow.md) — provider boundaries, structured output, prompt configuration, and human decisions
- [API reference](docs/api-reference.md) — endpoints grouped by capability
- [Operations](docs/operations.md) — configuration, deployment, logs, rebuilds, and shutdown
- [Serverless hackathon deployment roadmap](docs/serverless-hackathon-deployment-roadmap.md) — Vercel, Lambda, DynamoDB, Bedrock verification, cost controls, and teardown
- [Bedrock verification](docs/bedrock-verification.md) — reviewed Converse behavior, tests, IAM, and live smoke procedure
- [DynamoDB data model](docs/dynamodb-data-model.md) — keys, indexes, access patterns, chunking, and concurrency
- [Client integration contract](docs/client-integration-contract.md) — authoritative client endpoints and wire formats

## Repository layout

```text
client/                 Next.js application
server/app/api/         FastAPI route handlers
server/app/services/    application workflows
server/app/repositories/storage-neutral contracts and backend composition
server/app/domain/      domain models and validation
server/app/integrations client gateway and provider contracts
server/alembic/         database migrations
server/tests/           executable behavior documentation
docs/                   topic-focused project documentation
```
