# Getting started

Start the standalone demo client on port 8100 first. Configure the host platform with
`CLIENT_GATEWAY_URL=http://localhost:8100/integration/v1`; from the server container use
`http://host.docker.internal:8100/integration/v1` or a shared-network service name.

```bash
docker compose --env-file .env.local -f compose.dev.yml up -d --build --wait
docker compose --env-file .env.local -f compose.dev.yml exec server python -m app.seed
```

Open the client-connection page at <http://localhost:3000>, evidence at `/evidence`, and
sources at `/sources`. Seeding is repeatable and creates only a platform-owned manual
evidence source.

The Sources UI manages scraper creation, editing, enablement, immediate collection, and
deletion when no retained evidence references the source. The Evidence UI supports
manual creation, upload, editing, archive/restore, raw-content redaction, and permanent
deletion when audit protections allow it. Primary navigation is shared in the top bar.

Backend verification:

```bash
cd server
../.venv/bin/pytest -q
alembic upgrade head
```

Frontend verification:

```bash
cd client
npm run lint
npx tsc --noEmit
npm run build
```
