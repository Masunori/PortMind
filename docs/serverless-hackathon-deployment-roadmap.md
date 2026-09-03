# Serverless hackathon deployment roadmap

## Goal and constraints

Deploy the Next.js client on Vercel and the AEGIS API on AWS for a short-lived
hackathon while keeping AWS spend within the account's USD 20 limit. The target
AWS stack is Lambda Function URLs, DynamoDB on-demand, Bedrock on-demand,
CloudWatch Logs, and EventBridge Scheduler only if scheduled collection is needed.
Do not add ECS, EC2, RDS, ALB, API Gateway, NAT Gateway, OpenSearch, S3 document
storage, S3 Vectors, Cognito, or Bedrock Provisioned Throughput.

PostgreSQL remains the known-good local/reference persistence implementation. It is
not deployed as an automatic fallback and must never be selected automatically after
a DynamoDB failure. `PERSISTENCE_BACKEND=postgres|dynamodb` must be an explicit
operator choice; switching stores also requires intentionally providing or migrating
the applicable data.

## Definition of done for every iteration

Before changing code, read `README.md`, this roadmap, the relevant documents under
`docs/`, and applicable `AGENTS.md` files. Record a full test baseline. Preserve
unrelated worktree changes.

Every iteration must:

- update `README.md`, relevant `docs/` pages, configuration examples, and docstrings;
- add tests for its new behavior and run the complete backend and frontend suites;
- preserve all still-relevant behavior and tests from earlier iterations;
- update tests whose assumptions intentionally changed instead of merely deleting
  them, and document any retired test together with its replacement; and
- leave a short record of commands run, results, remaining risks, and rollback steps.

Tests must reflect the architecture at that iteration. While both persistence
implementations exist, shared repository contract tests must run against both.

## Iteration 0: baseline and deployment decisions

**Current input:** Dockerized Next.js, FastAPI, and PostgreSQL; an existing Bedrock
implementation awaiting review; a separately deployed authoritative client; and the
hackathon cost constraints above.

**Work:** Confirm AWS Region, Bedrock model/inference-profile ID, the externally
reachable `CLIENT_GATEWAY_URL`, whether scheduled collection is demo-critical, data
size limits, resource names, deletion date, and AWS SAM as the default IaC choice.
Run and record all existing tests before modifying the architecture.

**Expected output:** A recorded baseline, confirmed deployment parameters, an
authoritative-client hosting decision, an environment-variable inventory, cost
guardrails, and explicit accepted hackathon risks (public Function URL, no end-user
authentication, no production HA, and no retained original documents).

## Iteration 1: verify the existing Bedrock implementation

**Current input:** `server/app/integrations/bedrock.py`, the shared model behaviors,
provider factory and prompt service, Bedrock documentation, and the existing
`server/tests/test_bedrock_providers.py`. Another implementation session has already
written this code; do not assume that it is either incomplete or correct.

**Work:** Review transport, structured-output schemas, provider boundaries, prompt
selection, factory configuration, boto3 credential-chain use, async/thread behavior,
timeouts, retry multiplication, error sanitization, model/inference-profile resource
handling, panel concurrency, token limits, and metadata. Verify behavior against the
current Bedrock Converse API and the selected model in the chosen Region. Audit test
coverage before changing implementation. Add only fixes justified by the review.
Include at least one opt-in live smoke test that is skipped without explicit AWS test
configuration and has tightly bounded tokens and cost.

Tests should cover every provider role, valid structured responses, invalid JSON and
schema repair, semantic validation failure, missing response blocks, throttling,
quota/authentication errors, timeouts, SDK failures, configured attempt limits,
prompt overrides, factory defaults/overrides, panel limits and partial failures, and
the absence of static AWS credentials in deployment configuration.

**Expected output:** A written correctness and test-gap assessment; any necessary
fixes; sufficient deterministic contract tests; a bounded opt-in live smoke test;
and documented, least-privilege `bedrock:InvokeModel` permissions. No provider rewrite
should occur merely because this roadmap is being followed.

## Iteration 2: introduce a persistence boundary

**Current input:** Services coupled to SQLAlchemy models/sessions and PostgreSQL as
the behavioral reference.

**Work:** Introduce repository protocols for sources, evidence, signals, experiments,
planning cycles, and prompts. Move persistence operations behind those protocols and
centralize backend selection. Initially retain PostgreSQL behavior unchanged. Record
all reads, ordering rules, constraints, transactions, deletion checks, and
idempotency access patterns needed by the UI and workflows.

**Expected output:** Services depend on repository contracts rather than SQLAlchemy;
the PostgreSQL implementation and local Compose workflow still pass; and DynamoDB
can be added without changing domain/provider boundaries.

## Iteration 3: design the DynamoDB model

**Current input:** Repository contracts and documented access patterns.

**Work:** Design an on-demand table, primary/sort keys, only the GSIs required by
real queries, conditional writes, optimistic versions, transaction boundaries,
pagination, date/enum/Decimal serialization, due-source queries, content-hash
deduplication, and deletion-impact behavior. Define evidence-content chunking because
a DynamoDB item cannot hold arbitrarily large extracted text. Do not add S3.

**Expected output:** `docs/dynamodb-data-model.md` maps every repository method to a
bounded DynamoDB operation, contains example items/indexes, avoids normal-path table
scans, and defines maximum evidence size and concurrency semantics.

## Iteration 4: implement DynamoDB alongside PostgreSQL

**Current input:** Approved DynamoDB design, repository contracts, and PostgreSQL
contract behavior.

**Work:** Implement DynamoDB repositories and explicit
`PERSISTENCE_BACKEND=postgres|dynamodb` selection. Preserve PostgreSQL models,
Alembic migrations, Compose services, repository implementation, and tests as the
local/reference fallback. Add shared repository contract tests that execute against
both backends. Implement conditional idempotency, immutable signal versions,
pagination, content chunking, and application-level error translation. Provide an
idempotent DynamoDB demo seed.

Do not implement automatic runtime fallback, dual writes, or implicit synchronization
between PostgreSQL and DynamoDB. Those mechanisms could split workflow state across
stores. Keep separate dependency groups if PostgreSQL packages unnecessarily enlarge
the Lambda artifact.

**Expected output:** The complete application passes against DynamoDB; PostgreSQL
remains a tested local/reference option; switching is explicit and documented; and
the AWS deployment needs no PostgreSQL service. Existing migration tests remain for
the retained PostgreSQL implementation, while new initialization/contract tests
cover DynamoDB.

## Iteration 5: make FastAPI Lambda-compatible

**Current input:** FastAPI operating against either repository implementation, with
Uvicorn/Alembic/APScheduler assumptions still present.

**Work:** Add a Mangum Lambda handler while retaining Uvicorn locally. Ensure Lambda
startup does not run Alembic or APScheduler. Reuse SDK clients across warm invocations,
write temporary files only under `/tmp`, enforce request/evidence limits, and use the
Lambda execution role rather than access-key environment variables. Replace or
supplement database health with storage-backend health. Configure bounded timeout,
memory, and reserved concurrency.

**Expected output:** The same API passes ASGI tests and Function URL event tests,
runs locally with PostgreSQL, and runs in Lambda with DynamoDB and Bedrock.

## Iteration 6: measure workflows and add queues only if required

**Current input:** Lambda-compatible synchronous collection, Bedrock, planning, and
simulation workflows.

**Work:** Measure worst-case evidence processing, crawling, planner-panel, and client
simulation requests. Keep synchronous execution if rehearsals are reliable within a
conservative Lambda timeout. Otherwise add SQS only for the operations that need it,
return `202` plus a job ID, store status in DynamoDB, and make workers idempotent with
bounded retries and a dead-letter queue.

**Expected output:** A measured and documented synchronous decision, or the smallest
necessary queue/worker implementation. Tests cover timeouts, duplicate delivery,
retry exhaustion, and state transitions applicable to the chosen design.

## Iteration 7: replace or omit in-process scheduling

**Current input:** APScheduler coupled to application lifespan and a DynamoDB
due-source query.

**Decision:** Scheduled collection is optional and defaults off globally and per
scraper. Manual collection is the hackathon-safe default. If it becomes necessary for
judging, enable only selected scrapers and use EventBridge rather than an in-process
scheduler in Lambda.

**Work:** With scheduled collection disabled, document manual collection. If enabled,
use EventBridge Scheduler every 10-15 minutes to invoke
a bounded dispatcher/worker and acquire a conditional per-source lease. Never start
a scheduler in a Lambda web invocation.

**Expected output:** Either no scheduled AWS resource, or one scale-to-zero schedule
without duplicate source processing. Update/replace scheduler tests to match the
chosen iteration behavior.

## Iteration 8: deploy the frontend on Vercel

**Current input:** Existing Next.js 16 application and a deployed Lambda Function URL.

**Work:** Keep normal Next.js/SSR behavior and configure the Vercel project root as
`client`. Set `BACKEND_URL` and `NEXT_PUBLIC_API_URL` to the Function URL; never put
secrets in `NEXT_PUBLIC_*`. Add `robots` metadata and `public/robots.txt` with
`Disallow: /`. Verify loading/error states and Lambda cold-start behavior.

**Expected output:** The Vercel production URL renders server-side pages and completes
browser mutations against Lambda. It requests no indexing, but documentation clearly
states that no-index is not access control.

## Iteration 9: public endpoint, CORS, and SSRF safeguards

**Current input:** A Vercel production origin and Lambda Function URL with no user
authentication requirement.

**Work:** Use Function URL `AuthType=NONE`. Let exactly one layer own CORS, allow the
production Vercel origin, and test preflight/mutations. Decide explicitly whether
preview origins are supported. Harden source fetching against localhost, link-local,
metadata, private/reserved IPs, DNS rebinding, and redirect-based SSRF. Bound body,
page, redirect, and extracted-content sizes.

**Expected output:** The production UI works without duplicate CORS headers; obvious
internal-network fetches are rejected; and public-access risk is recorded.

## Iteration 10: connect the authoritative client

**Current input:** Lambda cannot use the local `localhost` or
`host.docker.internal` demo-client addresses.

**Work:** Provide a reachable HTTPS deployment for the authoritative client without
placing the general AEGIS Lambda behind a NAT Gateway. Store its token in an SSM
SecureString if needed and expose it only to Lambda. Exercise context, catalogs,
resolution, validation, simulation submission, polling, and results.

**Expected output:** Deployed `/health/client` succeeds and end-to-end experiment and
planning workflows work without exposing the client token to Vercel/browser code.

## Iteration 11: infrastructure as code and cost controls

**Current input:** Verified runtime components and final queue/scheduler decisions.

**Work:** Add an AWS SAM template for only the resources in use: DynamoDB, backend
Lambda and Function URL, IAM, short-retention log group, and optional EventBridge/SQS
resources. Parameterize Region, model, client URL/token parameter, CORS origin,
timeouts, memory, concurrency, log retention, and scheduling. Add budget notifications
at useful thresholds. Use Bedrock on-demand, low token/attempt limits, bounded panel
and crawl sizes, Lambda reserved concurrency around 2-3, worker concurrency 1, and
short log retention. Never log full evidence, prompts, responses, tokens, or
credentials.

**Expected output:** Repeatable validate/deploy/update/delete commands, scoped IAM,
CloudFormation outputs, a resource/cost inventory, and no always-on AWS resource.

## Iteration 12: deployed end-to-end rehearsal

**Current input:** Vercel frontend, AWS stack, reachable authoritative client, and all
local suites passing.

**Work:** Exercise health, source creation/collection, evidence processing, signal
review, experiment submission/results, complete planning flow, and prompt override
reset. Verify persistence across cold starts. Rehearse Bedrock/DynamoDB/client
failures, duplicate requests, browser refresh, throttling, and timeouts. Inspect logs
for both usefulness and data leakage. Record actual rehearsal cost.

**Expected output:** A judge-ready deployment, passing local and deployed smoke tests,
a demo runbook, known limitations, rollback steps, and measured cost.

## Iteration 13: demo freeze and teardown

**Current input:** A rehearsed deployment and deletion date.

**Work:** Seed stable demo data, verify quotas/endpoints/no-index behavior, freeze
deployments for judging, and prepare fallback screenshots. After judging, delete the
SAM stack and confirm removal of schedules, queues, functions, Function URLs, log
groups, DynamoDB data, SSM parameters, and unused IAM resources. Remove Vercel secrets
and disable/delete the deployment as appropriate. Review final billing.

**Expected output:** A stable demonstration followed by no remaining chargeable or
secret-bearing hackathon resources, with final cost and lessons documented in
`docs/demo-runbook.md` and `docs/teardown.md`.

## Critical path

```text
baseline and decisions
-> Bedrock verification
-> persistence boundary
-> DynamoDB design and implementation alongside PostgreSQL
-> Lambda compatibility
-> synchronous/queue and scheduler decisions
-> Vercel and public-endpoint hardening
-> authoritative-client connectivity
-> IaC and cost controls
-> rehearsal
-> teardown
```

The highest migration risk is reproducing relational lifecycle, ordering, deletion,
and idempotency behavior in DynamoDB. PostgreSQL contract behavior and the shared test
suite are the reference for detecting omissions; PostgreSQL is not a live automatic
failover system.
