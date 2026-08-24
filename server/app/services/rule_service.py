"""Persistence and static validation for declarative simulation rules."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.rule import RuleTrigger, SimulationRule, SimulationRuleCreate
from app.domain.schema import FieldBehavior, FieldDefinition, FieldType
from app.models import SchemaVersionRecord, SimulationRuleRecord
from app.services.context_version_service import bump_context_version


CORE_NUMERIC_SOURCES = {
    "edge.cost", "edge.transit_time_hours", "edge.capacity", "shipment.quantity"
}


def _domain(record: SimulationRuleRecord) -> SimulationRule:
    """Convert a persistence record to the public rule contract."""

    return SimulationRule(
        id=record.id,
        name=record.name,
        trigger=record.trigger,
        operation=record.operation,
        source=record.source,
        target_metric=record.target_metric,
        enabled=record.enabled,
        created_at=record.created_at,
    )


def _custom_numeric_sources() -> set[str]:
    """Return numeric flow fields exposed by immutable edge schemas."""

    with SessionLocal() as session:
        versions = session.scalars(select(SchemaVersionRecord)).all()
    sources = set()
    for version in versions:
        for raw in version.fields:
            field = FieldDefinition.model_validate(raw)
            if field.type in {FieldType.NUMBER, FieldType.INTEGER} and field.behavior is FieldBehavior.FLOW:
                sources.add(f"edge.attributes.{field.key}")
    return sources


def validate_rule(values: SimulationRuleCreate) -> None:
    """Reject unavailable triggers, fields, and nonnumeric sources."""

    if values.trigger is not RuleTrigger.EDGE_TRAVERSED:
        raise ValueError("Initial rule execution supports EDGE_TRAVERSED only")
    if values.source not in CORE_NUMERIC_SOURCES | _custom_numeric_sources():
        raise ValueError("Rule source is not an available numeric edge/shipment field")


def save_rule(values: SimulationRuleCreate) -> SimulationRule:
    """Create a unique validated rule."""

    validate_rule(values)
    with SessionLocal.begin() as session:
        if session.get(SimulationRuleRecord, values.id):
            raise ValueError("Rule ID already exists")
        record = SimulationRuleRecord(**values.model_dump(mode="json"), created_at=datetime.now(timezone.utc))
        session.add(record)
        bump_context_version(session)
    return _domain(record)


def get_rules(enabled_only: bool = False) -> list[SimulationRule]:
    """Return rules in stable order."""

    with SessionLocal() as session:
        statement = select(SimulationRuleRecord).order_by(SimulationRuleRecord.id)
        if enabled_only:
            statement = statement.where(SimulationRuleRecord.enabled.is_(True))
        return [_domain(item) for item in session.scalars(statement).all()]
