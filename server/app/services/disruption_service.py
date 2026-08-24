"""Persist and read deterministic supply-chain disruptions."""

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.disruption import Disruption, DisruptionEffects
from app.domain.schema import FieldDefinition, FieldType
from app.models import DisruptionRecord, EdgeRecord, NodeRecord, SchemaVersionRecord


def _validate_custom_effects(disruption: Disruption) -> None:
    """Require custom effect targets to be declared numeric entity fields."""

    if not disruption.effects.custom_effects:
        return
    with SessionLocal() as session:
        for effect in disruption.effects.custom_effects:
            entity_kind, _attributes, key = effect.target_field.split(".", 2)
            identifiers = (
                disruption.affected_node_ids
                if entity_kind == "node"
                else disruption.affected_edge_ids
            )
            model = NodeRecord if entity_kind == "node" else EdgeRecord
            if not identifiers:
                raise ValueError(
                    f"Custom effect {effect.target_field} has no affected {entity_kind} targets"
                )
            for identifier in identifiers:
                record = session.get(model, identifier)
                if record is None:
                    raise ValueError(f"Custom effect target {identifier} does not exist")
                version = session.get(SchemaVersionRecord, record.schema_version_id)
                definitions = {
                    item.key: item
                    for item in (
                        FieldDefinition.model_validate(raw)
                        for raw in (version.fields if version else [])
                    )
                }
                definition = definitions.get(key)
                if definition is None or definition.type not in {
                    FieldType.NUMBER,
                    FieldType.INTEGER,
                }:
                    raise ValueError(
                        f"Custom effect field {effect.target_field} is not a declared numeric field"
                    )


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

    _validate_custom_effects(disruption)
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
