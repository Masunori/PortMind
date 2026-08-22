"""Disruption domain models and supported deterministic effects."""

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class DisruptionType(str, Enum):
    """Identify the supported classes of supply-chain disruption."""

    PORT_CONGESTION = "PORT_CONGESTION"
    EDGE_CLOSURE = "EDGE_CLOSURE"
    TRANSIT_DELAY = "TRANSIT_DELAY"
    NODE_DELAY = "NODE_DELAY"
    CAPACITY_REDUCTION = "CAPACITY_REDUCTION"


class DisruptionEffects(BaseModel):
    """Describe optional deterministic modifiers applied by a disruption."""

    edge_disabled: bool = False
    transit_time_multiplier: float | None = Field(default=None, gt=0)
    node_handling_delay_hours: float | None = Field(default=None, ge=0)
    handling_time_multiplier: float | None = Field(default=None, gt=0)
    capacity_multiplier: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_effect(self) -> "DisruptionEffects":
        """Require at least one effect that changes simulation behavior."""

        if not self.edge_disabled and all(
            value is None
            for value in (
                self.transit_time_multiplier,
                self.node_handling_delay_hours,
                self.handling_time_multiplier,
                self.capacity_multiplier,
            )
        ):
            raise ValueError("At least one disruption effect is required")
        return self


class Disruption(BaseModel):
    """Represent a time-bounded set of network effects."""

    id: str
    type: DisruptionType
    enabled: bool = True
    affected_node_ids: list[str] = Field(default_factory=list)
    affected_edge_ids: list[str] = Field(default_factory=list)
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)
    effects: DisruptionEffects

    @model_validator(mode="after")
    def validate_window_and_targets(self) -> "Disruption":
        """Require an increasing time window and at least one target."""

        if self.end_time <= self.start_time:
            raise ValueError("Disruption end time must be after start time")
        if not self.affected_node_ids and not self.affected_edge_ids:
            raise ValueError("At least one affected node or edge is required")
        return self


class DisruptionToggle(BaseModel):
    """Request body for enabling or disabling a persisted disruption."""

    enabled: bool
