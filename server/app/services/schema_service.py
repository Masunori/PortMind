"""Immutable schema versioning and safe entity-attribute migration."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.network_management import ChangeImpact
from app.domain.schema import (
    EntityKind,
    EntitySchema,
    FieldDefinition,
    FieldType,
    SchemaCreate,
    SchemaVersionCreate,
    validate_field_value,
)
from app.models import EdgeRecord, EntitySchemaRecord, NodeRecord, SchemaVersionRecord, SimulationRuleRecord
from app.services.context_version_service import bump_context_version


def _domain(schema: EntitySchemaRecord, version: SchemaVersionRecord) -> EntitySchema:
    """Combine schema identity with its current immutable definition."""

    return EntitySchema(
        id=schema.id,
        name=schema.name,
        entity_kind=EntityKind(schema.entity_kind),
        current_version_id=version.id,
        version=version.version,
        fields=[FieldDefinition.model_validate(item) for item in version.fields],
        created_at=schema.created_at,
    )


def create_schema(values: SchemaCreate) -> EntitySchema:
    """Create a schema and immutable version one."""

    now = datetime.now(timezone.utc)
    version_id = f"{values.id}:v1"
    with SessionLocal.begin() as session:
        if session.get(EntitySchemaRecord, values.id):
            raise ValueError("Schema ID already exists")
        schema = EntitySchemaRecord(id=values.id, name=values.name, entity_kind=values.entity_kind.value, current_version_id=version_id, created_at=now)
        version = SchemaVersionRecord(id=version_id, schema_id=values.id, version=1, fields=[field.model_dump(mode="json") for field in values.fields], created_at=now)
        session.add_all([schema, version])
        bump_context_version(session)
    return _domain(schema, version)


def get_schemas(kind: EntityKind | None = None) -> list[EntitySchema]:
    """Return current schemas in stable order."""

    with SessionLocal() as session:
        statement = select(EntitySchemaRecord).order_by(EntitySchemaRecord.id)
        if kind: statement = statement.where(EntitySchemaRecord.entity_kind == kind.value)
        schemas = session.scalars(statement).all()
        return [_domain(item, session.get(SchemaVersionRecord, item.current_version_id)) for item in schemas]


def get_schema(schema_id: str) -> EntitySchema | None:
    """Return one current schema."""

    with SessionLocal() as session:
        schema = session.get(EntitySchemaRecord, schema_id)
        return _domain(schema, session.get(SchemaVersionRecord, schema.current_version_id)) if schema else None


def _safe_change(old: list[FieldDefinition], new: list[FieldDefinition]) -> None:
    """Reject destructive or type-changing schema edits."""

    previous = {field.key: field for field in old}
    proposed = {field.key: field for field in new}
    removed = set(previous) - set(proposed)
    if removed: raise ValueError(f"Fields cannot be removed: {', '.join(sorted(removed))}")
    for key, before in previous.items():
        after = proposed[key]
        if before.type != after.type: raise ValueError(f"Field {key} type cannot change")
        if before.unit != after.unit: raise ValueError(f"Field {key} unit cannot change")
        if before.behavior != after.behavior: raise ValueError(f"Field {key} behavior cannot change")
        if before.type is FieldType.ENUM and not set(before.enum_values) <= set(after.enum_values): raise ValueError(f"Enum values cannot be removed from {key}")
        if not before.required and after.required and after.default is None: raise ValueError(f"Required field {key} needs a default")
    for key in set(proposed) - set(previous):
        if proposed[key].required and proposed[key].default is None: raise ValueError(f"New required field {key} needs a default")


def preview_schema_version(schema_id: str, values: SchemaVersionCreate) -> ChangeImpact:
    """Validate a successor and count affected entities and rules."""

    schema = get_schema(schema_id)
    if schema is None: raise LookupError("Schema not found")
    _safe_change(schema.fields, values.fields)
    with SessionLocal() as session:
        model = NodeRecord if schema.entity_kind is EntityKind.NODE else EdgeRecord
        count = len(session.scalars(select(model).where(model.schema_version_id == schema.current_version_id)).all())
        field_keys = {field.key for field in schema.fields}
        rule_count = len([
            rule
            for rule in session.scalars(select(SimulationRuleRecord)).all()
            if rule.source.rsplit(".", 1)[-1] in field_keys
        ])
    return ChangeImpact(entity_count=count, rule_count=rule_count)


def create_schema_version(schema_id: str, values: SchemaVersionCreate) -> EntitySchema:
    """Create and apply a safe immutable successor version."""

    preview_schema_version(schema_id, values)
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        schema = session.get(EntitySchemaRecord, schema_id)
        old = session.get(SchemaVersionRecord, schema.current_version_id)
        number = old.version + 1
        version = SchemaVersionRecord(id=f"{schema_id}:v{number}", schema_id=schema_id, version=number, fields=[field.model_dump(mode="json") for field in values.fields], created_at=now)
        session.add(version)
        model = NodeRecord if schema.entity_kind == EntityKind.NODE.value else EdgeRecord
        entities = session.scalars(select(model).where(model.schema_version_id == old.id)).all()
        old_keys = {item["key"] for item in old.fields}
        for entity in entities:
            attributes = dict(entity.attributes or {})
            for field in values.fields:
                if field.key not in old_keys and field.key not in attributes and field.default is not None:
                    attributes[field.key] = field.default
            entity.attributes = attributes
            entity.schema_version_id = version.id
        schema.current_version_id = version.id
        bump_context_version(session)
    return _domain(schema, version)


def validate_entity_attributes(kind: str, version_id: str | None, attributes: dict[str, object]) -> None:
    """Validate entity attributes against an immutable schema version."""

    if version_id is None:
        if attributes: raise ValueError("Custom attributes require a schema version")
        return
    with SessionLocal() as session:
        version = session.get(SchemaVersionRecord, version_id)
        if version is None: raise ValueError("Schema version does not exist")
        schema = session.get(EntitySchemaRecord, version.schema_id)
    if schema.entity_kind != kind: raise ValueError("Schema kind does not match entity")
    definitions = {item.key: item for item in (FieldDefinition.model_validate(raw) for raw in version.fields)}
    unknown = set(attributes) - set(definitions)
    if unknown: raise ValueError(f"Unknown custom fields: {', '.join(sorted(unknown))}")
    for definition in definitions.values():
        if definition.required and definition.key not in attributes: raise ValueError(f"Required field {definition.key} is missing")
        if definition.key in attributes: validate_field_value(definition, attributes[definition.key])
