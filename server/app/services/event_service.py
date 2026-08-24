"""Group corroborating documents by type, entity, and overlapping time."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.database import SessionLocal
from app.models import EventDocumentRecord, IntelligenceEventRecord


def group_event(
    document_id: str,
    disruption_type: str,
    entity_ids: list[str],
    start_time: float,
    end_time: float,
) -> str:
    """Reuse a structurally matching event or create a new group."""

    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        events = session.scalars(
            select(IntelligenceEventRecord).where(
                IntelligenceEventRecord.disruption_type == disruption_type,
                IntelligenceEventRecord.start_time < end_time,
                IntelligenceEventRecord.end_time > start_time,
            )
        ).all()
        record = next(
            (item for item in events if set(item.affected_entity_ids) & set(entity_ids)),
            None,
        )
        if record is None:
            record = IntelligenceEventRecord(
                id=f"event-{uuid4().hex}",
                disruption_type=disruption_type,
                affected_entity_ids=entity_ids,
                start_time=start_time,
                end_time=end_time,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
        elif not set(entity_ids) <= set(record.affected_entity_ids):
            record.affected_entity_ids = sorted(set(record.affected_entity_ids) | set(entity_ids))
            record.updated_at = now
        existing = session.get(EventDocumentRecord, (record.id, document_id))
        if existing is None:
            session.add(
                EventDocumentRecord(
                    event_id=record.id, document_id=document_id, linked_at=now
                )
            )
    return record.id
