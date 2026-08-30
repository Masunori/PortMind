# AEGIS Platform

AEGIS is a simulation-agnostic evidence and experiment platform. It grounds signals against an authoritative client model, supports human review, and hands immutable experiments to a separately deployed client for execution.

The local stack provides:

- Next.js client: <http://localhost:3000>
- FastAPI server: <http://localhost:8000>
- Interactive API documentation: <http://localhost:8000/docs>
- PostgreSQL: `localhost:5432`

Every AI-assisted path uses deterministic stub providers by default. Local development requires no model account, API key, or cloud service.
The ingestion filter and interpreter can optionally use Gemini structured output; see
[AI and workflow](docs/ai-and-workflow.md) and [operations](docs/operations.md) for the
provider boundaries, retry behavior, and configuration.

## Quick start

Prerequisite: Docker Engine or Docker Desktop with Docker Compose v2.

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
```

The platform owns evidence, assessments, signals, reviews, scenarios, workflow records, and normalized result copies. The client integration owns operational data, entity identifiers, model state, disruption contracts, simulation logic, and authoritative results.

## Documentation

Start with the [documentation index](docs/README.md), or jump directly to:

- [Getting started](docs/getting-started.md) — setup, migrations, tests, and code-reading path
- [Architecture](docs/architecture.md) — ownership, gateways, providers, validation, and persistence
- [Ingestion and review](docs/ingestion-and-review.md) — sources, evidence, filtering, grounding, and lifecycle
- [Simulation and planning](docs/simulation-and-planning.md) — scenarios, contingency plans, ranking, and experiments
- [AI and workflow](docs/ai-and-workflow.md) — provider boundaries, LangGraph, runs, and human decisions
- [API reference](docs/api-reference.md) — endpoints grouped by capability
- [Operations](docs/operations.md) — configuration, deployment, logs, rebuilds, and shutdown
- [Client integration contract](docs/client-integration-contract.md) — authoritative client endpoints and wire formats

## Repository layout

```text
client/                 Next.js application
server/app/api/         FastAPI route handlers
server/app/services/    workflows and persistence operations
server/app/domain/      domain models and validation
server/app/integrations client gateway and provider contracts
server/alembic/         database migrations
server/tests/           executable behavior documentation
docs/                   topic-focused project documentation
```
