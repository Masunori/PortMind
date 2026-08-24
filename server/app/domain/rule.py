"""Safe declarative simulation rule contracts."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RuleOperation(str, Enum):
    """Supported deterministic numeric operations."""

    SET = "SET"
    ADD = "ADD"
    SUBTRACT = "SUBTRACT"
    MULTIPLY = "MULTIPLY"
    MIN = "MIN"
    MAX = "MAX"


class RuleTrigger(str, Enum):
    """Supported simulation lifecycle hooks."""

    SIMULATION_START = "SIMULATION_START"
    EDGE_TRAVERSED = "EDGE_TRAVERSED"
    NODE_ENTERED = "NODE_ENTERED"
    NODE_EXITED = "NODE_EXITED"
    SHIPMENT_ARRIVED = "SHIPMENT_ARRIVED"
    DISRUPTION_STARTED = "DISRUPTION_STARTED"
    DISRUPTION_ENDED = "DISRUPTION_ENDED"


class SimulationRuleCreate(BaseModel):
    """Create a rule from a fixed source and operation vocabulary."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,99}$")
    name: str = Field(min_length=1, max_length=200)
    trigger: RuleTrigger
    operation: RuleOperation
    source: str
    target_metric: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    enabled: bool = True


class SimulationRule(SimulationRuleCreate):
    """Expose a persisted declarative rule."""

    created_at: datetime
