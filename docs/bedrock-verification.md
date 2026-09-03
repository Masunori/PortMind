# Bedrock implementation verification

This document records serverless-roadmap Iteration 1. The adapter uses Bedrock
Runtime `Converse`, accepts a foundation-model ID or inference-profile ID/ARN in
`modelId`, and requests JSON Schema structured output. Vendor-neutral prompts,
schemas, semantic checks, and domain conversion remain in `model_provider.py`;
`bedrock.py` owns only transport, correction attempts, error translation, and trusted
request metadata.

## Review outcome

- boto3 uses its normal credential chain. Compose does not copy access-key variables
  into containers; use a mounted local profile for development and an execution role
  in AWS.
- synchronous boto3 calls run in a worker thread. The runtime client is cached on the
  provider instance for connection reuse.
- `BEDROCK_MAX_ATTEMPTS` bounds schema/semantic correction calls and
  `BEDROCK_SDK_MAX_ATTEMPTS` separately bounds SDK transport attempts. With defaults,
  one provider operation can make at most six HTTP attempts.
- connect/read timeouts and output tokens are bounded. API, authentication, quota,
  timeout, and SDK errors are translated without reflecting provider messages.
- panel calls are concurrent, capped at five roles, and retain successful proposals
  when another role fails.
- deterministic tests cover all five provider roles, structured schemas, invalid JSON,
  schema and semantic repair, missing blocks, throttling, authentication, timeouts,
  SDK failures, attempt limits, prompt overrides/factory selection, panel bounds, and
  partial panel failures.

Bedrock compiles a new structured-output grammar on first use, so an initial request
can take materially longer than a warm request. Deployment timeout rehearsal must
include both cases.

## Bounded live smoke test

The live test is skipped unless explicitly enabled. It performs one Filter call with
one SDK attempt, one schema attempt, a 20-second timeout, and at most 256 output tokens:

```bash
cd server
BEDROCK_LIVE_TEST=1 \
BEDROCK_REGION=ap-southeast-1 \
BEDROCK_MODEL_ID=replace-with-approved-model-or-profile \
pytest -q tests/test_bedrock_providers.py -k live
```

Do not enable it in the ordinary deterministic suite. The selected model/profile and
Region still require an operator confirmation before deployment.

## Least-privilege runtime permission

Converse requires `bedrock:InvokeModel`. Scope the resource to the selected model or
inference profile and, for cross-Region inference, the destination foundation-model
resources required by that profile. Replace the placeholders after the deployment
decision is confirmed:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "bedrock:InvokeModel",
    "Resource": [
      "arn:aws:bedrock:REGION:ACCOUNT_ID:inference-profile/PROFILE_ID",
      "arn:aws:bedrock:*::foundation-model/MODEL_ID"
    ]
  }]
}
```

Do not grant `bedrock:*`, provisioned-throughput actions, or model-management actions.

## Verification record

On 2026-09-03, before these fixes, frontend tests (2 files), ESLint, and TypeScript
passed. The full backend baseline could not run because the Docker daemon was absent
and host Python lacked pytest, SQLAlchemy, and boto3. The attempted command was:

```bash
CLIENT_GATEWAY_URL=http://host.docker.internal:8100/integration/v1 \
docker compose -f compose.dev.yml run --rm server pytest
```

After rebuilding the development server image, the complete backend suite passed with
145 tests and one intentionally skipped opt-in live Bedrock smoke test. Python bytecode
compilation, frontend tests, ESLint, TypeScript, and both Compose configuration renders
also passed. The production Next.js build could not be
completed in this restricted runner: Turbopack was denied permission to bind its
internal worker port, while the webpack fallback failed parsing TypeScript
`--showConfig`. Neither failure identified an application compile error.

Rollback this iteration by reverting the Bedrock adapter/factory/tests, removing
`BEDROCK_SDK_MAX_ATTEMPTS`, and restoring the prior Compose provider configuration.
No persisted data or migrations are involved. Remaining risks are the unconfirmed
deployment parameters and the pending opt-in live smoke test.
