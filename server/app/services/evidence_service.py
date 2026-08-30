"""Normalized evidence persistence, deduplication, and retention lifecycle."""

from datetime import datetime, timezone
import hashlib
import json
import re
from uuid import uuid4

from sqlalchemy import func, select

from app.database import SessionLocal
from app.integrations.contracts import (
    DeletionImpact, DuplicateDeletionCandidate, DuplicateDeletionPreview,
    DuplicateDeletionResult, Evidence, EvidenceCreate, EvidenceKind, EvidenceUpdate,
    ProcessingStatus,
)
from app.models import (
    DataSourceRecord, EvidenceRecord, SignalEvidenceRecord,
)


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _digest(values: EvidenceCreate) -> str:
    if values.content is not None:
        raw = _normalized_text(values.content)
    elif values.structured_content is not None:
        raw = json.dumps(values.structured_content, sort_keys=True, separators=(",", ":"))
    else:
        raw = values.content_reference or ""
    return hashlib.sha256(raw.encode()).hexdigest()


def _to_domain(record: EvidenceRecord) -> Evidence:
    return Evidence(id=record.id, source_id=record.source_id, collection_run_id=record.collection_run_id,
        kind=record.kind, title=record.title, media_type=record.media_type, content=record.content,
        structured_content=record.structured_content, content_reference=record.content_reference,
        content_hash=record.content_hash, duplicate_of_id=record.duplicate_of_id, source_url=record.source_url,
        published_at=record.published_at, collected_at=record.collected_at, processed_at=record.processed_at,
        processing_status=record.processing_status, parser_warnings=record.parser_warnings or [],
        quality_metadata=record.quality_metadata or {}, retention_class=record.retention_class,
        expires_at=record.expires_at, archived_at=record.archived_at)


def store_evidence(values: EvidenceCreate) -> tuple[Evidence, bool]:
    """Store an envelope; duplicates keep provenance but do not copy raw content."""

    now = datetime.now(timezone.utc); digest = _digest(values)
    with SessionLocal.begin() as session:
        if session.get(DataSourceRecord, values.source_id) is None: raise LookupError("Source not found")
        original = session.scalar(select(EvidenceRecord).where(
            EvidenceRecord.content_hash == digest, EvidenceRecord.duplicate_of_id.is_(None)).order_by(EvidenceRecord.created_at))
        record = EvidenceRecord(id=f"evidence-{uuid4().hex}", source_id=values.source_id,
            collection_run_id=values.collection_run_id, kind=values.kind.value,
            title=values.title, media_type=values.media_type,
            content=None if original else (_normalized_text(values.content) if values.content is not None else None),
            structured_content=None if original else values.structured_content,
            content_reference=None if original else values.content_reference, content_hash=digest,
            duplicate_of_id=original.id if original else None, source_url=values.source_url,
            published_at=values.published_at, collected_at=values.collected_at or now,
            processed_at=now if values.processing_status != ProcessingStatus.PENDING else None,
            processing_status=values.processing_status.value, parser_warnings=values.parser_warnings,
            quality_metadata=values.quality_metadata, retention_class=values.retention_class.value,
            expires_at=values.expires_at, archived_at=None, raw_removed_at=None, legal_hold=False, created_at=now)
        session.add(record)
    return _to_domain(record), original is not None


def list_evidence(*, archived: bool | None = False, kind: EvidenceKind | None = None,
                  include_duplicates: bool = False, limit: int = 50,
                  offset: int = 0) -> list[Evidence]:
    query = select(EvidenceRecord)
    if archived is True: query = query.where(EvidenceRecord.archived_at.is_not(None))
    elif archived is False: query = query.where(EvidenceRecord.archived_at.is_(None))
    if kind: query = query.where(EvidenceRecord.kind == kind.value)
    if not include_duplicates:
        query = query.where(EvidenceRecord.duplicate_of_id.is_(None))
    query = query.order_by(EvidenceRecord.collected_at.desc(), EvidenceRecord.id).offset(offset).limit(limit)
    with SessionLocal() as session: records = session.scalars(query).all()
    return [_to_domain(item) for item in records]


def get_evidence(evidence_id: str) -> Evidence | None:
    with SessionLocal() as session: record = session.get(EvidenceRecord, evidence_id)
    return _to_domain(record) if record else None


def evidence_has_signal(evidence_id: str) -> bool:
    """Return whether immutable signal history already references evidence."""

    with SessionLocal() as session:
        return bool(session.scalar(select(func.count()).select_from(
            SignalEvidenceRecord).where(SignalEvidenceRecord.evidence_id == evidence_id)))


def set_archived(evidence_id: str, archived: bool) -> Evidence:
    with SessionLocal.begin() as session:
        record = session.get(EvidenceRecord, evidence_id)
        if record is None: raise LookupError("Evidence not found")
        record.archived_at = datetime.now(timezone.utc) if archived else None
    return _to_domain(record)


def _deletion_impact(session, record: EvidenceRecord) -> DeletionImpact:
    signal_count = session.scalar(select(func.count()).select_from(SignalEvidenceRecord).where(
        SignalEvidenceRecord.evidence_id == record.id)) or 0
    duplicate_count = session.scalar(select(func.count()).select_from(EvidenceRecord).where(
        EvidenceRecord.duplicate_of_id == record.id)) or 0
    protected = ((["signal_versions"] if signal_count else [])
                 + (["duplicate_evidence"] if duplicate_count else [])
                 + (["legal_hold"] if record.legal_hold else []))
    return DeletionImpact(evidence_id=record.id, can_remove_raw_content=not record.legal_hold,
        can_delete_permanently=not protected, protected_by=protected,
        raw_content_present=any((record.content, record.structured_content, record.content_reference)))


def deletion_impact(evidence_id: str) -> DeletionImpact:
    with SessionLocal() as session:
        record = session.get(EvidenceRecord, evidence_id)
        if record is None: raise LookupError("Evidence not found")
        return _deletion_impact(session, record)


def duplicate_deletion_preview(evidence_id: str) -> DuplicateDeletionPreview:
    """Preview direct duplicate cleanup without changing provenance records."""
    with SessionLocal() as session:
        canonical = session.get(EvidenceRecord, evidence_id)
        if canonical is None: raise LookupError("Evidence not found")
        if canonical.duplicate_of_id is not None:
            raise ValueError("Batch cleanup must target canonical evidence")
        duplicates = list(session.scalars(select(EvidenceRecord).where(
            EvidenceRecord.duplicate_of_id == evidence_id).order_by(EvidenceRecord.collected_at,
                                                                     EvidenceRecord.id)))
        candidates = []
        for item in duplicates:
            impact = _deletion_impact(session, item)
            candidates.append(DuplicateDeletionCandidate(evidence_id=item.id,
                can_delete=impact.can_delete_permanently, protected_by=impact.protected_by))
        return DuplicateDeletionPreview(canonical_evidence_id=evidence_id, candidates=candidates)


def delete_unprotected_duplicates(evidence_id: str, *,
                                  delete_canonical: bool = False) -> DuplicateDeletionResult:
    """Delete eligible direct duplicates in one transaction and report protected skips."""
    with SessionLocal.begin() as session:
        canonical = session.get(EvidenceRecord, evidence_id)
        if canonical is None: raise LookupError("Evidence not found")
        if canonical.duplicate_of_id is not None:
            raise ValueError("Batch cleanup must target canonical evidence")
        duplicates = list(session.scalars(select(EvidenceRecord).where(
            EvidenceRecord.duplicate_of_id == evidence_id).order_by(EvidenceRecord.collected_at,
                                                                     EvidenceRecord.id)))
        deleted_ids = []; skipped = []
        for item in duplicates:
            impact = _deletion_impact(session, item)
            if impact.can_delete_permanently:
                deleted_ids.append(item.id); session.delete(item)
            else:
                skipped.append(DuplicateDeletionCandidate(evidence_id=item.id,
                    can_delete=False, protected_by=impact.protected_by))
        session.flush()
        canonical_deleted = False
        if delete_canonical and _deletion_impact(session, canonical).can_delete_permanently:
            session.delete(canonical); canonical_deleted = True
    return DuplicateDeletionResult(canonical_evidence_id=evidence_id,
        deleted_ids=deleted_ids, skipped=skipped, canonical_deleted=canonical_deleted)


def remove_raw_content(evidence_id: str) -> Evidence:
    impact = deletion_impact(evidence_id)
    if not impact.can_remove_raw_content: raise PermissionError("Evidence is on legal hold")
    with SessionLocal.begin() as session:
        record = session.get(EvidenceRecord, evidence_id)
        record.content = None; record.structured_content = None; record.content_reference = "removed://retained-audit-metadata"
        record.raw_removed_at = datetime.now(timezone.utc)
    return _to_domain(record)


def update_evidence(evidence_id: str, values: EvidenceUpdate) -> Evidence:
    """Edit unprotected evidence while retaining its stable platform identifier."""

    impact = deletion_impact(evidence_id)
    if impact.protected_by:
        raise PermissionError("Evidence linked to an audit workflow cannot be edited")
    changes = values.model_dump(exclude_unset=True)
    with SessionLocal.begin() as session:
        record = session.get(EvidenceRecord, evidence_id)
        if record is None:
            raise LookupError("Evidence not found")
        for field, value in changes.items():
            setattr(record, field, _normalized_text(value) if field == "content" and value else value)
        if "content" in changes or "content_reference" in changes:
            candidate = EvidenceCreate(source_id=record.source_id, kind=record.kind,
                title=record.title, media_type=record.media_type, content=record.content,
                structured_content=record.structured_content, content_reference=record.content_reference,
                source_url=record.source_url, quality_metadata=record.quality_metadata)
            record.content_hash = _digest(candidate)
            record.processed_at = datetime.now(timezone.utc)
    return _to_domain(record)


def delete_evidence(evidence_id: str) -> None:
    """Permanently delete evidence only when no audit record protects it."""

    impact = deletion_impact(evidence_id)
    if not impact.can_delete_permanently:
        raise PermissionError("Evidence linked to an audit workflow cannot be deleted")
    with SessionLocal.begin() as session:
        record = session.get(EvidenceRecord, evidence_id)
        if record is None:
            raise LookupError("Evidence not found")
        session.delete(record)
