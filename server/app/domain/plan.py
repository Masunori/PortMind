"""Contingency plan actions and deterministic comparison contracts."""

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class PlanActionType(str, Enum):
    """Identify the supported deterministic contingency interventions."""

    REROUTE_SHIPMENT = "REROUTE_SHIPMENT"
    EXPEDITE_SHIPMENT = "EXPEDITE_SHIPMENT"
    USE_ALTERNATIVE_INVENTORY = "USE_ALTERNATIVE_INVENTORY"
    WAIT = "WAIT"


class PlanStatus(str, Enum):
    """Track the human-decision lifecycle of a contingency plan."""

    GENERATED = "GENERATED"
    RECOMMENDED = "RECOMMENDED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PlanAction(BaseModel):
    """Describe one intervention applied before a simulation starts."""

    type: PlanActionType
    shipment_id: str | None = None
    new_route: list[str] | None = None
    alternative_inventory_node_id: str | None = None
    transit_time_multiplier: float = Field(default=1, gt=0)
    cost_multiplier: float = Field(default=1, ge=0)

    @model_validator(mode="after")
    def validate_action_fields(self) -> "PlanAction":
        """Require the fields needed by each supported action type."""

        if self.type is PlanActionType.WAIT:
            return self
        if self.shipment_id is None:
            raise ValueError(f"{self.type.value} requires shipment_id")
        if self.type is PlanActionType.REROUTE_SHIPMENT and not self.new_route:
            raise ValueError("REROUTE_SHIPMENT requires new_route")
        if self.type is PlanActionType.USE_ALTERNATIVE_INVENTORY:
            if self.alternative_inventory_node_id is None:
                raise ValueError(
                    "USE_ALTERNATIVE_INVENTORY requires alternative_inventory_node_id"
                )
            if not self.new_route:
                raise ValueError("USE_ALTERNATIVE_INVENTORY requires new_route")
        return self


class Plan(BaseModel):
    """Represent a named collection of explicit contingency actions."""

    id: str
    name: str
    actions: list[PlanAction]
    status: PlanStatus = PlanStatus.GENERATED


class PlanScenarioResult(BaseModel):
    """Summarize one plan and scenario combination against baseline."""

    plan_id: str
    plan_name: str
    scenario_id: str
    scenario_name: str
    probability: float = Field(ge=0, le=1)
    total_cost: float = Field(ge=0)
    average_lead_time_hours: float = Field(ge=0)
    delay_hours: float = Field(ge=0)
    late_shipments: int = Field(ge=0)
