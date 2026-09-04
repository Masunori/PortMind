"""PostgreSQL source repository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import SessionLocal
from app.domain.source import DataSource, DataSourceCreate, DataSourceUpdate, SourceRunStatus, SourceType
from app.models import DataSourceRecord, EvidenceRecord, SourceCollectionLeaseRecord
from app.repositories.contracts import Page
from app.repositories.errors import ConflictError, NotFoundError
from app.repositories.postgres.common import decode_offset, encode_offset, translate, validate_limit


def _domain(record: DataSourceRecord) -> DataSource:
    return DataSource(id=record.id, name=record.name, type=SourceType(record.type),
        description=record.description, url=record.url, enabled=record.enabled,
        schedule_enabled=record.schedule_enabled, scrape_interval_minutes=record.scrape_interval_minutes,
        scraper_type=record.scraper_type, scraper_config_json=record.scraper_config_json,
        last_run_at=record.last_run_at, next_run_at=record.next_run_at,
        last_status=SourceRunStatus(record.last_status), last_error=record.last_error,
        created_at=record.created_at, updated_at=record.updated_at)


class PostgresSourceRepository:
    def __init__(self, session_factory=None): self.session_factory = session_factory or SessionLocal

    def create(self, values: DataSourceCreate) -> DataSource:
        now = datetime.now(timezone.utc)
        slug = re.sub(r"[^a-z0-9]+", "-", values.name.casefold()).strip("-") or "source"
        next_run = now + timedelta(minutes=values.scrape_interval_minutes) if (
            values.type is SourceType.WEBSITE and values.enabled and values.schedule_enabled) else None
        record = DataSourceRecord(id=f"{slug}-{uuid4().hex[:8]}", **values.model_dump(mode="python", exclude={"type"}),
            type=values.type.value, last_run_at=None, next_run_at=next_run,
            last_status=SourceRunStatus.NEVER.value, last_error=None, created_at=now, updated_at=now)
        try:
            with self.session_factory.begin() as session: session.add(record)
        except SQLAlchemyError as error: translate(error)
        return _domain(record)

    def list(self, *, limit: int = 100, continuation_token: str | None = None) -> Page[DataSource]:
        validate_limit(limit); offset = decode_offset(continuation_token)
        try:
            with self.session_factory() as session:
                rows = session.scalars(select(DataSourceRecord).order_by(
                    func.lower(DataSourceRecord.name), DataSourceRecord.id).offset(offset).limit(limit + 1)).all()
        except SQLAlchemyError as error: translate(error)
        token = encode_offset(offset, limit) if len(rows) > limit else None
        return Page(tuple(_domain(row) for row in rows[:limit]), token)

    def get(self, source_id: str) -> DataSource | None:
        try:
            with self.session_factory() as session: record = session.get(DataSourceRecord, source_id)
        except SQLAlchemyError as error: translate(error)
        return _domain(record) if record else None

    def update(self, source_id: str, values: DataSourceUpdate) -> DataSource | None:
        try:
            with self.session_factory.begin() as session:
                record = session.get(DataSourceRecord, source_id)
                if record is None: return None
                candidate = DataSourceCreate.model_validate({
                    "name": record.name, "type": record.type, "description": record.description,
                    "url": record.url, "enabled": record.enabled, "schedule_enabled": record.schedule_enabled,
                    "scrape_interval_minutes": record.scrape_interval_minutes, "scraper_type": record.scraper_type,
                    "scraper_config_json": record.scraper_config_json, **values.model_dump(exclude_unset=True)})
                for field, value in candidate.model_dump().items(): setattr(record, field, value)
                now = datetime.now(timezone.utc); record.updated_at = now
                record.next_run_at = now + timedelta(minutes=record.scrape_interval_minutes) if (
                    record.type == SourceType.WEBSITE.value and record.enabled and record.schedule_enabled
                    and record.scrape_interval_minutes is not None) else None
        except SQLAlchemyError as error: translate(error)
        return _domain(record)

    def delete(self, source_id: str) -> bool:
        try:
            with self.session_factory.begin() as session:
                record = session.get(DataSourceRecord, source_id)
                if record is None: return False
                count = session.scalar(select(func.count()).select_from(EvidenceRecord).where(EvidenceRecord.source_id == source_id)) or 0
                if count: raise ConflictError("Sources with retained evidence cannot be deleted")
                session.delete(record)
        except SQLAlchemyError as error: translate(error)
        return True

    def due(self, now: datetime | None = None) -> list[DataSource]:
        effective = now or datetime.now(timezone.utc)
        try:
            with self.session_factory() as session:
                rows = session.scalars(select(DataSourceRecord).where(
                    DataSourceRecord.type == SourceType.WEBSITE.value, DataSourceRecord.enabled.is_(True),
                    DataSourceRecord.schedule_enabled.is_(True), DataSourceRecord.next_run_at <= effective
                ).order_by(DataSourceRecord.next_run_at, DataSourceRecord.id)).all()
        except SQLAlchemyError as error: translate(error)
        return [_domain(row) for row in rows]

    def record_run(self, source_id: str, error: str | None = None) -> DataSource:
        now = datetime.now(timezone.utc)
        try:
            with self.session_factory.begin() as session:
                record = session.get(DataSourceRecord, source_id)
                if record is None: raise NotFoundError("Source not found")
                record.last_run_at = now; record.last_status = (SourceRunStatus.FAILED if error else SourceRunStatus.HEALTHY).value
                record.last_error = error; record.updated_at = now
                record.next_run_at = now + timedelta(minutes=record.scrape_interval_minutes) if (
                    record.enabled and record.schedule_enabled and record.scrape_interval_minutes is not None) else None
        except SQLAlchemyError as sql_error: translate(sql_error)
        return _domain(record)

    def acquire_lease(self,source_id:str,owner:str,*,now:datetime,expires_at:datetime)->bool:
        try:
            with self.session_factory.begin() as session:
                lease=session.scalar(select(SourceCollectionLeaseRecord).where(SourceCollectionLeaseRecord.source_id==source_id).with_for_update())
                if lease is None:session.add(SourceCollectionLeaseRecord(source_id=source_id,owner=owner,expires_at=expires_at))
                elif (lease.expires_at.replace(tzinfo=timezone.utc) if lease.expires_at.tzinfo is None else lease.expires_at)>now:return False
                else:lease.owner=owner;lease.expires_at=expires_at
        except IntegrityError:return False
        except SQLAlchemyError as error:translate(error)
        return True

    def release_lease(self,source_id:str,owner:str)->None:
        try:
            with self.session_factory.begin() as session:
                lease=session.get(SourceCollectionLeaseRecord,source_id)
                if lease is not None and lease.owner==owner:session.delete(lease)
        except SQLAlchemyError as error:translate(error)
