# Ingestion and review

Uploads, websites, feeds, APIs, structured records, and manual entries all write
directly to canonical `evidence`. Content hashes deduplicate raw content while retaining
provenance. Scheduled website collection is bounded by same-site, robots, depth, page,
path, and keyword controls.

Automatic collection is opt-in twice: `ENABLE_SOURCE_SCHEDULER=true` starts the local
process scheduler, and each website scraper must independently enable its schedule.
Both defaults are off. The Sources UI displays global and per-scraper state; manual
collection remains available while automatic scheduling is off. Lambda deployments
must not start this in-process scheduler and may later use the same per-source setting
from an EventBridge dispatcher if scheduled collection is retained.

Evidence assessment and signal interpretation preserve provider metadata separately
from deterministic review state. Hypothetical signals cannot claim supporting
evidence. Unresolved or ambiguous entities remain review-blocking, and accepted signals
retain the client context and disruption catalog versions used for grounding.

Filtering and interpretation are protocol-based. By default, deterministic stubs make
local runs repeatable. When configured for Bedrock, the filter classifies evidence into
`ACCEPT`, `REVIEW`, `REJECT`, or `QUARANTINE`; only accepted evidence proceeds to the
interpreter. The interpreter proposes classification, signal type, textual entity
mentions, time window, probability, severity, and extraction confidence. Both adapters
request structured JSON and enforce the existing Pydantic contracts locally, with
bounded correction attempts for schema-invalid answers.

Signal types are constrained to the exact types in the client's current
`/disruption-contracts` catalog. That catalog is provided to the interpreter as
untrusted capability data and the same snapshot is reused during mapping.

Interpretation separates `entity_mentions` from `target_entity_mentions`. All
operational entities explicitly present in evidence are grounded and retained for
context. Only target entities are checked against the selected disruption contract and
sent to effect mapping as `target_ids`. An unresolved related entity therefore remains
visible without incorrectly blocking a valid mapping for a resolved target. Historical
entity rows created before this distinction are conservatively treated as targets.

## Rejected-signal reprocessing

Rejecting a candidate preserves its immutable signal, mapping outcome, provider
metadata, and evidence provenance. When every signal attempt for an evidence item is
rejected, the Evidence workspace enables **Reprocess**. Reprocessing creates a new
pending `SignalRecord` whose `retry_of_signal_id` points to the most recent rejected
attempt; it never overwrites or reopens the rejected record. A pending or accepted
attempt blocks further retries, preventing multiple active candidates for the same
evidence in normal operation.

Evidence remains protected from permanent deletion while any signal history refers to
it, including rejected history. Archive and raw-content removal remain the appropriate
retention-safe actions. A destructive purge of rejected history is intentionally not
part of ordinary evidence management.

Mapping is synchronous. Unexpected local mapping exceptions are persisted as terminal
`MAPPING_FAILED` / `PROCESSING_FAILED` outcomes with a safe retry message, so the UI
does not imply that background work is continuing. Nullable JSON Schema type unions
advertised by the client are supported during local payload validation.

If Bedrock remains rate-limited after the SDK retry policy is exhausted, collection stops invoking the
provider for that run and marks the current and remaining new evidence as deferred.
The evidence remains stored. Use **Process / retry** on its Evidence card, or call
`POST /api/evidence/{id}/process`, after provider capacity recovers; this does not
scrape the source again. Evidence already linked to signal history and duplicate
occurrence records cannot be reprocessed through this endpoint.

Schema compliance does not make an LLM answer operationally authoritative. Entity
mentions are grounded through the client gateway, mapped disruptions pass local JSON
Schema validation and client semantic validation, and signals still require human
review before activation.

The former raw-document, assessment, intelligence-event, and disruption-candidate
workflow has been removed. No compatibility table or API remains.

## Evidence deletion and duplicates

Permanent deletion is intentionally blocked when evidence is referenced by signal
history, duplicate provenance, or legal hold. The Evidence workspace previews this
impact before sending `DELETE`, explains the blocker, and offers archive or raw-content
removal as audit-safe alternatives.

Canonical evidence is hidden from permanent deletion while duplicate records point to
it. Enable **Include duplicates** in the Evidence workspace, review and remove the
dependent duplicate records first, then retry the canonical item. Duplicate records
are labelled with the canonical evidence ID they reference.

Canonical evidence cards also provide **Delete unprotected duplicates**. A preview
counts eligible and protected direct duplicates before confirmation. The deletion runs
in one database transaction, removes only eligible records, and reports every skipped
protected record. API callers may request `delete_canonical=true`; the canonical record
is deleted only if it is unprotected after duplicate cleanup.

Collection continues to retain lightweight duplicate occurrence records by default.
The batch operation deliberately does not replace canonical content or erase protected
provenance.
