"""Directed transport-edge domain model."""

from pydantic import BaseModel, Field


class Edge(BaseModel):
    """Represent a transport connection between two network nodes."""

    id: str
    source_id: str
    target_id: str
    mode: str
    transit_time_hours: float = Field(gt=0)
    cost: float = Field(ge=0)
    capacity: float = Field(ge=0)
    schema_version_id: str | None = None
    attributes: dict[str, object] = Field(default_factory=dict)
