"""Mutation and impact contracts for the live digital twin."""

from pydantic import BaseModel, Field


class NodeUpdate(BaseModel):
    """Editable node fields; identifiers remain immutable."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = Field(default=None, min_length=1, max_length=50)
    inventory: float | None = Field(default=None, ge=0)
    capacity: float | None = Field(default=None, ge=0)
    schema_version_id: str | None = None
    attributes: dict[str, object] | None = None


class EdgeUpdate(BaseModel):
    """Editable edge fields; identifiers remain immutable."""

    source_id: str | None = None
    target_id: str | None = None
    mode: str | None = Field(default=None, min_length=1, max_length=50)
    transit_time_hours: float | None = Field(default=None, gt=0)
    cost: float | None = Field(default=None, ge=0)
    capacity: float | None = Field(default=None, ge=0)
    schema_version_id: str | None = None
    attributes: dict[str, object] | None = None


class ChangeImpact(BaseModel):
    """Summarize records affected by a proposed destructive change."""

    entity_count: int = 0
    edge_count: int = 0
    shipment_count: int = 0
    disruption_count: int = 0
    alias_count: int = 0
    rule_count: int = 0
    blockers: list[str] = Field(default_factory=list)


class ContextVersion(BaseModel):
    """Expose the canonical network context generation."""

    version: int
