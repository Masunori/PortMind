"""Persist and read deterministic supply-chain disruptions."""

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.disruption import Disruption, DisruptionEffects
from app.models import DisruptionRecord


def _to_domain(record: DisruptionRecord) -> Disruption:
    """Convert one persisted disruption into its domain representation."""

    return Disruption(
        id=record.id,
        type=record.type,
        enabled=record.enabled,
        affected_node_ids=record.affected_node_ids,
        affected_edge_ids=record.affected_edge_ids,
        start_time=record.start_time,
        end_time=record.end_time,
        effects=DisruptionEffects.model_validate(record.effects),
    )


def save_disruption(disruption: Disruption) -> Disruption:
    """Create or replace a disruption with the same identifier."""

    with SessionLocal.begin() as session:
        record = session.merge(
            DisruptionRecord(
                id=disruption.id,
                type=disruption.type.value,
                enabled=disruption.enabled,
                affected_node_ids=disruption.affected_node_ids,
                affected_edge_ids=disruption.affected_edge_ids,
                start_time=disruption.start_time,
                end_time=disruption.end_time,
                effects=disruption.effects.model_dump(mode="json"),
            )
        )

    return _to_domain(record)


def get_disruptions(enabled_only: bool = False) -> list[Disruption]:
    """Return persisted disruptions, optionally limited to enabled records."""

    with SessionLocal() as session:
        statement = select(DisruptionRecord).order_by(DisruptionRecord.id)
        if enabled_only:
            statement = statement.where(DisruptionRecord.enabled.is_(True))
        records = session.scalars(statement).all()
        return [_to_domain(record) for record in records]


def get_disruption(disruption_id: str) -> Disruption | None:
    """Return one disruption by identifier or ``None`` when absent."""

    with SessionLocal() as session:
        record = session.get(DisruptionRecord, disruption_id)
        return _to_domain(record) if record is not None else None


def set_disruption_enabled(
    disruption_id: str,
    enabled: bool,
) -> Disruption | None:
    """Set one disruption's enabled state or return ``None`` if absent."""

    with SessionLocal.begin() as session:
        record = session.get(DisruptionRecord, disruption_id)
        if record is None:
            return None
        record.enabled = enabled

    return _to_domain(record)
