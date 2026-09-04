"""Platform-owned scenario definitions using client-normalized envelopes."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Scenario(BaseModel):
    """Group normalized disruptions under a scenario-level probability."""

    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    probability: float = Field(ge=0, le=1)
    disruptions: list[dict[str, Any]]
