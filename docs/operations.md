# Operations

## Integration configuration

Provider defaults remain deterministic, but the client gateway is always remote:

```dotenv
FILTER_PROVIDER=stub
RISK_PROVIDER=stub
PLANNER_PROVIDER=stub
INTERPRETER_PROVIDER=stub
RELATIONSHIP_PROVIDER=stub
EFFECT_MAPPING_PROVIDER=stub
GEMINI_API_KEY=replace-me
GEMINI_MODEL=gemini-flash-lite-latest
GEMINI_MAX_ATTEMPTS=3
GEMINI_TIMEOUT_SECONDS=30
HYPOTHESIS_PROVIDER=gemini
CLIENT_GATEWAY_URL=http://localhost:8100/integration/v1
CLIENT_GATEWAY_TOKEN=replace-me
CLIENT_GATEWAY_TIMEOUT_SECONDS=10
CLIENT_GATEWAY_MAX_RETRIES=2
```

`FILTER_PROVIDER` and `INTERPRETER_PROVIDER` accept `stub` or `gemini`; each can be
switched independently. The remaining provider settings currently accept only `stub`.
The Gemini key is required only when at least one Gemini provider is selected. Keep the
key in `.env.local`, never commit it, and rebuild/restart the server after changing
Compose environment values:

```bash
docker compose --env-file .env.local -f compose.dev.yml up -d --build server
docker compose --env-file .env.local -f compose.dev.yml logs -f server
```

`GEMINI_MAX_ATTEMPTS=3` means one initial structured-output request plus at most two
schema-correction requests. Reducing it lowers latency and cost; increasing it can
recover more malformed outputs but makes a single ingestion item more expensive. API
authentication, quota, rate-limit, and other HTTP errors fail immediately rather than
consuming schema-repair attempts.

To run only the provider contract tests without contacting Gemini:

```bash
docker compose -f compose.dev.yml exec server pytest tests/test_gemini_providers.py
```

`HTTPClientGateway` adds correlation and idempotency headers, bounded timeouts and retries, strict response validation, and stable errors.
There is no local operational-data fallback. Missing `CLIENT_GATEWAY_URL` fails clearly
when the gateway dependency is constructed. Start the demo client first and point the
URL at its versioned integration API. `FakeClientGateway` under `server/tests/fakes/`
is test-only.

When the platform server runs inside Docker and the demo client runs on the host, use
`http://host.docker.internal:8100/integration/v1` instead of the host-side URL above.

### Client validation failures

Disruption and intervention validation requests include the catalog version advertised
by the connected client. A client-side 4xx response is surfaced by planning as a
sanitized 502 integration error instead of an internal traceback. Check that the client
and platform images were rebuilt against compatible integration contracts.

The deterministic risk stub generates an ordered example window (`effective_from`
before `effective_until`). For nullable JSON Schema unions such as
`{"type": ["string", "null"]}`, it deterministically chooses the first concrete
non-null type so required fixture fields remain useful. Real providers remain
untrusted: their payloads are checked against the advertised JSON Schema and then
against the client's semantic validation rules before a scenario draft is stored.

## Other environment variables

- `DATABASE_URL` — server database connection; Compose uses hostname `database`, while host tools use `localhost:5432`.
- `ENABLE_SOURCE_SCHEDULER` — enable periodic source collection.
- `NEXT_PUBLIC_API_URL` — browser-accessible API URL compiled into the client.
- `CLIENT_ORIGIN` — exact browser origin allowed by FastAPI.
- `GEMINI_API_KEY` — Google AI API key, required by selected Gemini providers.
- `GEMINI_MODEL` — Gemini model shared by filter and interpreter providers.
- `GEMINI_MAX_ATTEMPTS` — total structured-output validation attempts; minimum `1`.
- `GEMINI_TIMEOUT_SECONDS` — timeout for each Gemini HTTP request.
- `HYPOTHESIS_PROVIDER` — `gemini` or `stub`; defaults to Gemini when a key exists and
  otherwise to the deterministic stub.

## Development operations

```bash
docker compose --env-file .env.local -f compose.dev.yml ps
docker compose --env-file .env.local -f compose.dev.yml logs -f
docker compose --env-file .env.local -f compose.dev.yml up -d --build server
docker compose --env-file .env.local -f compose.dev.yml down
```

To also delete the development database and build volumes:

```bash
docker compose --env-file .env.local -f compose.dev.yml down --volumes
```

## Production-like environment

Set production values in `.env.local`, then run:

```bash
docker compose --env-file .env.local -f compose.prod.yml up -d --build
docker compose --env-file .env.local -f compose.prod.yml ps
docker compose --env-file .env.local -f compose.prod.yml logs -f
```

Stop without deleting PostgreSQL data:

```bash
docker compose --env-file .env.local -f compose.prod.yml down
```

Production data uses the `postgres_prod_data` volume. Do not add `--volumes` unless deletion is intentional.
