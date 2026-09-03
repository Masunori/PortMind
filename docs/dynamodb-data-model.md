# DynamoDB data model

This is the implementation contract for the hackathon DynamoDB backend. PostgreSQL
remains the behavioral reference; selecting a backend never falls back or dual-writes.

## Table and indexes

Use one on-demand table with string keys `PK` and `SK`, deletion TTL attribute `ttl`,
and optimistic integer `version`. Resource name is parameterized.

- Primary key: aggregate-local reads and bounded child collections.
- `GSI1PK`/`GSI1SK`: type lists in stable application order.
- `GSI2PK`/`GSI2SK`: sparse operational lookups: due sources, content hashes, and
  experiment idempotency keys.

No repository method performs `Scan`. List methods require a bounded `limit` and
opaque continuation token containing the DynamoDB exclusive-start key.

| Entity | PK | SK | Index use |
| --- | --- | --- | --- |
| Source | `SOURCE#id` | `META` | GSI1 `SOURCE` / `name#id`; GSI2 `DUE` / `next_run_at#id` only while enabled and scheduled |
| Evidence metadata | `EVIDENCE#id` | `META` | GSI1 `EVIDENCE` / `collected_at#id`; GSI2 `HASH#sha256` / `collected_at#id` |
| Evidence chunk | `EVIDENCE#id` | `CONTENT#000001` | none |
| Assessment | `EVIDENCE#id` | `ASSESSMENT#time#id` | none |
| Signal | `SIGNAL#id` | `META` | GSI1 `SIGNAL` / reverse-created-time plus ID |
| Signal version | `SIGNAL#id` | `VERSION#000001` | GSI2 `SIGNAL_VERSION#id` / `META` |
| Signal evidence/entity/effect/relationship | `SIGNAL#id` | typed immutable child key | relationship lookup keys only where required |
| Experiment | `EXPERIMENT#id` | `META` | GSI1 list; GSI2 `EXPERIMENT_KEY#hash` / `META` |
| Result copy | `EXPERIMENT#id` | `RESULT#run_id` | none |
| Planning cycle | `PLANNING#id` | `META` | GSI1 `PLANNING` / reverse-updated-time plus ID |
| Prompt override | `PROMPT#agent` | `META` | none; known agent keys are batch-read |

Scenario and plan definition items follow the same `TYPE#id`/`META` pattern and their
existing stable-ID ordering on GSI1.

## Repository operation mapping

- Sources: point get/write/delete; ordered list through GSI1; due-source query through
  the sparse `DUE` partition. Enabling scheduling adds the GSI2 keys; disabling it
  removes them. Run completion conditionally advances `next_run_at`.
- Evidence: transact source-existence check, conditional hash/id write, and chunks.
  Lists use GSI1; deletion impact queries the evidence aggregate and bounded reverse
  references. Duplicate cleanup uses a transaction and returns protected skips.
- Signals: an aggregate query returns metadata and immutable children. Creating a
  version transactionally asserts its number/current pointer. Review updates require
  the expected `version`; immutable version items are never overwritten.
- Experiments: GSI2 resolves the idempotency key; `attribute_not_exists(PK)` prevents
  duplicate creation. Submission/result transitions require expected status/version.
- Planning cycles: point reads and conditional snapshot replacement. Large snapshots
  are split into deterministic `SECTION#name#chunk` children before the item limit.
- Prompts: point gets/writes/deletes for the fixed allow-listed agent names.

Foreign-key behavior is reproduced with explicit checks. Source deletion checks the
source-evidence reference partition; evidence deletion checks signal and duplicate
references; experiment/result records are retained. Multi-item invariants use
`TransactWriteItems` and never exceed 100 unique items.

## Content limits and serialization

The API accepts at most 256 KiB of extracted UTF-8 evidence text. Content is stored in
chunks of at most 64 KiB UTF-8 bytes, with byte count, SHA-256, chunk count, and media
type on metadata. Four chunks therefore fit the application limit while every item
stays well below DynamoDB's 400 KB maximum. Original uploaded documents are not
retained in DynamoDB or S3.

Datetimes are UTC ISO-8601 strings with `Z`; enum values are strings; floats are
converted through decimal strings to `Decimal`; sets are stored as ordered lists when
order is observable. Empty values are normalized consistently. Continuation tokens
are URL-safe base64 JSON and are validated before use.

## Concurrency and failure semantics

Every mutable aggregate has `version`. Updates use `version = :expected` and increment
on success; conditional failures become domain conflict errors. Content/idempotency
creation uses `attribute_not_exists`. A scheduled collector must acquire a short
conditional lease (`lease_until`, `lease_owner`) before fetching and clears or expires
it after recording the run. Repository errors are translated to stable not-found,
conflict, validation, throttling, or unavailable errors. They never trigger a
PostgreSQL fallback.

On-demand capacity has no idle throughput charge. The SAM template should additionally
set conservative table/GSI maximum throughput and alarms to contain accidental usage.
