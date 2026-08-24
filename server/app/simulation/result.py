"""Public output contract for deterministic simulations."""

from pydantic import BaseModel, Field


class SimulationResult(BaseModel):
    """Summarize costs, timing, late shipments, and final inventory."""

    total_cost: float = Field(ge=0)
    average_lead_time_hours: float = Field(ge=0)
    average_delay_hours: float = Field(ge=0)
    late_shipments: int = Field(ge=0)
    final_inventory: dict[str, float]
    custom_metrics: dict[str, float] = Field(default_factory=dict)
