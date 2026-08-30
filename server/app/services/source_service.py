"""CRUD operations for user-facing ingestion sources."""

from datetime import datetime, timedelta, timezone
import re
from uuid import uuid4

from sqlalchemy import func, select

from app.database import SessionLocal
from app.domain.source import (
    DataSource,
    DataSourceCreate,
    DataSourceUpdate,
    SourceRunStatus,
    SourceType,
)
from app.models import DataSourceRecord, EvidenceRecord


def _to_domain(record: DataSourceRecord) -> DataSource:
    """Convert one source record into its public domain contract."""

    return DataSource(
        id=record.id,
        name=record.name,
        type=SourceType(record.type),
        description=record.description,
        url=record.url,
        enabled=record.enabled,
        scrape_interval_minutes=record.scrape_interval_minutes,
        scraper_type=record.scraper_type,
        scraper_config_json=record.scraper_config_json,
        last_run_at=record.last_run_at,
        next_run_at=record.next_run_at,
        last_status=SourceRunStatus(record.last_status),
        last_error=record.last_error,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _identifier(name: str) -> str:
    """Create a readable unique source identifier."""

    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "source"
    return f"{slug}-{uuid4().hex[:8]}"


def create_source(values: DataSourceCreate) -> DataSource:
    """Persist a new independently configured source."""

    now = datetime.now(timezone.utc)
    next_run = (
        now + timedelta(minutes=values.scrape_interval_minutes)
        if values.type is SourceType.WEBSITE and values.enabled
        else None
    )
    record = DataSourceRecord(
        id=_identifier(values.name),
        name=values.name,
        type=values.type.value,
        description=values.description,
        url=values.url,
        enabled=values.enabled,
        scrape_interval_minutes=values.scrape_interval_minutes,
        scraper_type=values.scraper_type,
        scraper_config_json=values.scraper_config_json,
        last_run_at=None,
        next_run_at=next_run,
        last_status=SourceRunStatus.NEVER.value,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    with SessionLocal.begin() as session:
        session.add(record)
    return _to_domain(record)


def get_sources() -> list[DataSource]:
    """Return sources in stable name and identifier order."""

    with SessionLocal() as session:
        records = session.scalars(
            select(DataSourceRecord).order_by(DataSourceRecord.name, DataSourceRecord.id)
        ).all()
    return [_to_domain(record) for record in records]


def get_source(source_id: str) -> DataSource | None:
    """Return one source by identifier or ``None``."""

    with SessionLocal() as session:
        record = session.get(DataSourceRecord, source_id)
        return _to_domain(record) if record is not None else None


def update_source(source_id: str, values: DataSourceUpdate) -> DataSource | None:
    """Apply a partial source-management update."""

    with SessionLocal.begin() as session:
        record = session.get(DataSourceRecord, source_id)
        if record is None:
            return None
        changes = values.model_dump(exclude_unset=True)
        candidate = DataSourceCreate.model_validate(
            {
                "name": record.name,
                "type": record.type,
                "description": record.description,
                "url": record.url,
                "enabled": record.enabled,
                "scrape_interval_minutes": record.scrape_interval_minutes,
                "scraper_type": record.scraper_type,
                "scraper_config_json": record.scraper_config_json,
                **changes,
            }
        )
        for field, value in candidate.model_dump().items():
            setattr(record, field, value)
        now = datetime.now(timezone.utc)
        record.updated_at = now
        record.next_run_at = (
            now + timedelta(minutes=record.scrape_interval_minutes)
            if record.type == SourceType.WEBSITE.value
            and record.enabled
            and record.scrape_interval_minutes is not None
            else None
        )
    return _to_domain(record)


def delete_source(source_id: str) -> bool:
    """Delete a source and report whether it existed."""

    with SessionLocal.begin() as session:
        record = session.get(DataSourceRecord, source_id)
        if record is None:
            return False
        evidence_count = session.scalar(select(func.count()).select_from(EvidenceRecord).where(
            EvidenceRecord.source_id == source_id)) or 0
        if evidence_count:
            raise PermissionError("Sources with retained evidence cannot be deleted")
        session.delete(record)
    return True


def get_due_sources(now: datetime | None = None) -> list[DataSource]:
    """Return enabled website sources whose independent schedule is due."""

    effective_now = now or datetime.now(timezone.utc)
    with SessionLocal() as session:
        records = session.scalars(
            select(DataSourceRecord)
            .where(
                DataSourceRecord.type == SourceType.WEBSITE.value,
                DataSourceRecord.enabled.is_(True),
                DataSourceRecord.next_run_at <= effective_now,
            )
            .order_by(DataSourceRecord.next_run_at, DataSourceRecord.id)
        ).all()
    return [_to_domain(record) for record in records]


def record_source_run(source_id: str, error: str | None = None) -> DataSource:
    """Persist collection health and calculate the source's next run."""

    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        record = session.get(DataSourceRecord, source_id)
        if record is None:
            raise LookupError("Source not found")
        record.last_run_at = now
        record.last_status = (
            SourceRunStatus.FAILED.value if error else SourceRunStatus.HEALTHY.value
        )
        record.last_error = error
        record.updated_at = now
        record.next_run_at = (
            now + timedelta(minutes=record.scrape_interval_minutes)
            if record.enabled and record.scrape_interval_minutes is not None
            else None
        )
    return _to_domain(record)
