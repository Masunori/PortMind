# Operations

## Integration configuration

Provider defaults remain deterministic, but the client gateway is always remote:

```dotenv
FILTER_PROVIDER=bedrock
RISK_PROVIDER=bedrock
PLANNER_PROVIDER=bedrock
INTERPRETER_PROVIDER=bedrock
RELATIONSHIP_PROVIDER=stub
EFFECT_MAPPING_PROVIDER=stub
HYPOTHESIS_PROVIDER=bedrock
BEDROCK_REGION=ap-southeast-1
BEDROCK_MODEL_ID=global.amazon.nova-2-lite-v1:0
BEDROCK_MAX_ATTEMPTS=3
BEDROCK_SDK_MAX_ATTEMPTS=2
BEDROCK_TIMEOUT_SECONDS=60
BEDROCK_MAX_TOKENS=4096
CLIENT_GATEWAY_URL=http://localhost:8100/integration/v1
CLIENT_GATEWAY_TOKEN=replace-me
CLIENT_GATEWAY_TIMEOUT_SECONDS=10
CLIENT_GATEWAY_MAX_RETRIES=2
ENABLE_SOURCE_SCHEDULER=false
```

`FILTER_PROVIDER`, `INTERPRETER_PROVIDER`, `RISK_PROVIDER`, and `PLANNER_PROVIDER`
accept `stub`, `bedrock`, or the retained `gemini` compatibility adapter; each can be
switched independently. Panel mode uses Bedrock when `PLANNER_PROVIDER=bedrock`, or the deterministic role panel when it
is `stub`.
Bedrock obtains credentials from boto3's standard credential chain. Prefer workload
roles or local AWS profiles over storing credentials in `.env.local`. Rebuild/restart
the server after changing Compose environment values:

```bash
docker compose --env-file .env.local -f compose.dev.yml up -d --build server
docker compose --env-file .env.local -f compose.dev.yml logs -f server
```

`BEDROCK_MAX_ATTEMPTS=3` means one initial structured-output request plus at most two
schema-correction requests. `BEDROCK_SDK_MAX_ATTEMPTS=2` independently bounds each
request's transport attempts, making the worst case six HTTP attempts. Reducing either
limit lowers latency and cost. API
authentication, quota, rate-limit, and other HTTP errors fail immediately rather than
consuming schema-repair attempts.

To run only the Bedrock provider contract tests without contacting AWS:

```bash
docker compose -f compose.dev.yml exec server pytest tests/test_bedrock_providers.py
```

`HTTPClientGateway` adds correlation and idempotency headers, bounded timeouts and retries, strict response validation, and stable errors.
There is no local operational-data fallback. Missing `CLIENT_GATEWAY_URL` fails clearly
when the gateway dependency is constructed. Start the demo client first and point the
URL at its versioned integration API. `FakeClientGateway` under `server/tests/fakes/`
is test-only.

### Provider prompt overrides

Operators can edit the Bedrock filter, interpreter, and planner system prompts in the
Prompts UI or through `/api/settings/prompts`. Overrides are stored in the platform
database and take effect when a provider is next constructed; resetting an override
restores the built-in default. Stub providers ignore these prompts. Prompt changes do
not bypass structured-output validation, client validation, or human review.

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
- `ENABLE_SOURCE_SCHEDULER` — global opt-in for local periodic source collection;
  defaults to `false`. Only enabled website sources with their independent
  `schedule_enabled` option set are collected. Manual **Collect now** requests do
  not require this switch.
- `NEXT_PUBLIC_API_URL` — browser-accessible API URL compiled into the client.
- `CLIENT_ORIGIN` — exact browser origin allowed by FastAPI.
- `BEDROCK_REGION` — AWS Region used by the Bedrock Runtime client.
- `BEDROCK_MODEL_ID` — foundation-model ID or inference-profile ID used by all Bedrock providers.
- `BEDROCK_MAX_ATTEMPTS` — total structured-output and semantic-correction attempts; minimum `1`.
- `BEDROCK_SDK_MAX_ATTEMPTS` — total SDK transport attempts per structured-output request; minimum `1`.
- `BEDROCK_TIMEOUT_SECONDS` — SDK connect and read timeout.
- `BEDROCK_MAX_TOKENS` — maximum tokens requested from Converse.
- `HYPOTHESIS_PROVIDER` — `bedrock`, `gemini`, or `stub`; defaults to Bedrock when a
  Bedrock model ID is configured and otherwise to the deterministic stub.

## Development operations

### DynamoDB Local foundation tests

The local emulator verifies the table schema and repository adapters. Start it on host
port `8001`:

```bash
docker compose -f compose.dev.yml --profile dynamodb up -d dynamodb-local
cd server
DYNAMODB_LOCAL_ENDPOINT=http://127.0.0.1:8001 \
  ../.venv/bin/pytest -q tests/test_dynamodb_foundation.py \
  tests/test_dynamodb_codec.py tests/test_dynamodb_local.py
```

The fixture uses Region `ap-southeast-1` by default; override it with
`DYNAMODB_LOCAL_REGION`. Each test table is named `psa-test-<uuid>`, created on demand,
and deleted after the test. A failed test may leave an isolated table; restart the
in-memory container to clear all local data:

```bash
docker compose -f compose.dev.yml --profile dynamodb restart dynamodb-local
```

If the integration test is skipped, set `DYNAMODB_LOCAL_ENDPOINT`. Connection failures
usually mean the profile service is not running or port `8001` is occupied. Remote
endpoints are deliberately rejected so tests cannot create or delete tables in an AWS
account.

To run the application on the emulator, create its table once and explicitly select
the backend:

```bash
cd server
AWS_ACCESS_KEY_ID=localTestKey AWS_SECRET_ACCESS_KEY=localTestSecret \
AWS_REGION=ap-southeast-1 ../.venv/bin/python -c \
  "import boto3; from app.repositories.dynamodb.schema import create_table; create_table(boto3.resource('dynamodb', region_name='ap-southeast-1', endpoint_url='http://127.0.0.1:8001'), 'psa-local')"
cd ..
PERSISTENCE_BACKEND=dynamodb docker compose -f compose.dev.yml --profile dynamodb up -d
```

Production requires `PERSISTENCE_BACKEND=dynamodb`, `DYNAMODB_TABLE_NAME`, and
`AWS_REGION`; omit `DYNAMODB_ENDPOINT_URL` in AWS. Credentials come from boto3's
workload-role/profile chain. The [SAM template](../infrastructure/template.yaml)
creates the encrypted on-demand table, TTL, point-in-time recovery, and a policy with
point, query, batch, and transaction actions but no table-wide read.

SDK requests use standard retry mode with four attempts. Conditional, throttling,
validation, authentication, timeout, transport, and service failures map to sanitized
application persistence errors. They never cause backend switching.

For rollback, stop writers, restore a point-in-time backup to a new table, update
`DYNAMODB_TABLE_NAME`, and redeploy. PostgreSQL fallback is not automatic and requires
a separately planned data migration. Alarm on throttles, system errors, latency, and
unexpected request growth; apply on-demand throughput limits where Region support
allows it.

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

## Lambda runtime

AWS Lambda invokes `app.main.handler`, a Mangum adapter around the same FastAPI app.
Its ASGI lifespan is disabled, so Lambda web invocations never start APScheduler or
run Alembic. Apply migrations or initialize the selected persistence backend as a
separate deployment operation. Uvicorn retains lifespan behavior for local use.

The Vercel client emits both `robots` no-index metadata and `/robots.txt` with
`Disallow: /`. These are crawler requests, not authentication or access control.

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
