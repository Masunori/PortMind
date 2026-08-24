"""Supply-chain node domain model."""

from pydantic import BaseModel, Field


class Node(BaseModel):
    """Represent a physical or commercial location in the network."""

    id: str
    name: str
    type: str
    inventory: float = Field(ge=0)
    capacity: float = Field(ge=0)
    schema_version_id: str | None = None
    attributes: dict[str, object] = Field(default_factory=dict)
