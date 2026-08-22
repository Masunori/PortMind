"""Scenario domain and simulation result models."""

from pydantic import BaseModel, Field

from app.domain.disruption import Disruption


class Scenario(BaseModel):
    """Represent a weighted collection of deterministic disruptions."""

    id: str
    name: str
    probability: float = Field(ge=0, le=1)
    disruptions: list[Disruption]


class ScenarioSimulationResult(BaseModel):
    """Summarize one scenario simulation relative to baseline."""

    scenario_id: str
    name: str
    probability: float
    total_cost: float = Field(ge=0)
    average_lead_time_hours: float = Field(ge=0)
    delay_hours: float = Field(ge=0)
    late_shipments: int = Field(ge=0)
