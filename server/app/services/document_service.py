"""Persistence and content-addressed deduplication for raw documents."""

from datetime import datetime, timezone
import hashlib
import re
from uuid import uuid4

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.document import DocumentCreate, DocumentStatus, RawDocument
from app.models import DataSourceRecord, RawDocumentRecord


def normalize_text(value: str) -> str:
    """Collapse insignificant whitespace while retaining paragraph boundaries."""

    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def content_hash(value: str) -> str:
    """Return a stable SHA-256 hash for normalized text."""

    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def _to_domain(record: RawDocumentRecord) -> RawDocument:
    """Convert a persistence record into the public document contract."""

    return RawDocument(
        id=record.id,
        source_id=record.source_id,
        title=record.title,
        source_url=record.source_url,
        media_type=record.media_type,
        content=record.content,
        content_hash=record.content_hash,
        status=DocumentStatus(record.status),
        error=record.error,
        collected_at=record.collected_at,
        created_at=record.created_at,
    )


def store_document(values: DocumentCreate) -> tuple[RawDocument, bool]:
    """Persist unique normalized content per source and return creation state."""

    normalized = normalize_text(values.content)
    digest = content_hash(normalized)
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        if session.get(DataSourceRecord, values.source_id) is None:
            raise LookupError("Source not found")
        existing = session.scalar(
            select(RawDocumentRecord).where(
                RawDocumentRecord.source_id == values.source_id,
                RawDocumentRecord.content_hash == digest,
            )
        )
        if existing is not None:
            return _to_domain(existing), False
        record = RawDocumentRecord(
            id=f"document-{uuid4().hex}",
            source_id=values.source_id,
            title=values.title,
            source_url=values.source_url,
            media_type=values.media_type,
            content=normalized,
            content_hash=digest,
            status=DocumentStatus.NEW.value,
            error=None,
            collected_at=values.collected_at or now,
            created_at=now,
        )
        session.add(record)
    return _to_domain(record), True


def get_documents(source_id: str | None = None) -> list[RawDocument]:
    """List documents newest first, optionally filtered by source."""

    query = select(RawDocumentRecord)
    if source_id is not None:
        query = query.where(RawDocumentRecord.source_id == source_id)
    query = query.order_by(RawDocumentRecord.collected_at.desc(), RawDocumentRecord.id)
    with SessionLocal() as session:
        records = session.scalars(query).all()
    return [_to_domain(record) for record in records]


def get_document(document_id: str) -> RawDocument | None:
    """Return one raw document or ``None``."""

    with SessionLocal() as session:
        record = session.get(RawDocumentRecord, document_id)
        return _to_domain(record) if record is not None else None
