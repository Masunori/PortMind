"""Mutable state accumulated while a simulation is running."""

from dataclasses import dataclass, field


@dataclass
class SimulationState:
    """Track time, cost, inventory, locations, and completion metrics."""

    current_time_hours: float = 0
    total_cost: float = 0
    inventory: dict[str, float] = field(default_factory=dict)
    shipment_locations: dict[str, str] = field(default_factory=dict)
    lead_times: dict[str, float] = field(default_factory=dict)
    late_shipments: set[str] = field(default_factory=set)
    custom_metrics: dict[str, float] = field(default_factory=dict)
