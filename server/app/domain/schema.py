"""Versioned typed extension schemas for network entities."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class EntityKind(str, Enum):
    """Identify schema ownership."""

    NODE = "NODE"
    EDGE = "EDGE"


class FieldType(str, Enum):
    """Supported non-executable attribute types."""

    NUMBER = "NUMBER"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    STRING = "STRING"
    ENUM = "ENUM"


class FieldBehavior(str, Enum):
    """Classify how an extension field participates in simulation."""

    STATIC = "STATIC"
    STATE = "STATE"
    FLOW = "FLOW"
    METRIC = "METRIC"


class FieldDefinition(BaseModel):
    """Define one typed attribute without executable expressions."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    label: str = Field(min_length=1, max_length=100)
    type: FieldType
    required: bool = False
    default: object | None = None
    unit: str | None = Field(default=None, max_length=30)
    enum_values: list[str] = Field(default_factory=list)
    behavior: FieldBehavior = FieldBehavior.STATIC

    @model_validator(mode="after")
    def validate_definition(self) -> "FieldDefinition":
        """Require compatible defaults and enum definitions."""

        if self.required and self.default is None:
            raise ValueError("Required custom fields need a default")
        if self.type is FieldType.ENUM and not self.enum_values:
            raise ValueError("Enum fields need at least one value")
        validate_field_value(self, self.default, allow_none=True)
        return self


def validate_field_value(
    definition: FieldDefinition, value: object, allow_none: bool = False
) -> None:
    """Reject attribute values that do not match their declared type."""

    if value is None and (allow_none or not definition.required):
        return
    valid = {
        FieldType.NUMBER: isinstance(value, (int, float)) and not isinstance(value, bool),
        FieldType.INTEGER: isinstance(value, int) and not isinstance(value, bool),
        FieldType.BOOLEAN: isinstance(value, bool),
        FieldType.STRING: isinstance(value, str),
        FieldType.ENUM: isinstance(value, str) and value in definition.enum_values,
    }[definition.type]
    if not valid:
        raise ValueError(f"Field {definition.key} expects {definition.type.value}")


class SchemaCreate(BaseModel):
    """Create the first immutable version of an entity schema."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,99}$")
    name: str = Field(min_length=1, max_length=200)
    entity_kind: EntityKind
    fields: list[FieldDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_fields(self) -> "SchemaCreate":
        """Require unique custom keys and protect core fields."""

        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Custom field keys must be unique")
        core = {"id", "name", "type", "capacity", "inventory", "source_id", "target_id", "mode", "cost", "transit_time_hours"}
        if set(keys) & core:
            raise ValueError("Custom fields cannot replace core fields")
        return self


class SchemaVersionCreate(BaseModel):
    """Request a safe successor version."""

    fields: list[FieldDefinition]


class EntitySchema(BaseModel):
    """Expose a schema and its current immutable version."""

    id: str
    name: str
    entity_kind: EntityKind
    current_version_id: str
    version: int
    fields: list[FieldDefinition]
    created_at: datetime
