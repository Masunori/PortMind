"""Ordered events processed by the deterministic simulation queue."""

from dataclasses import dataclass, field
from enum import Enum


class EventType(str, Enum):
    """Identify whether a shipment departs from or arrives at a node."""

    DEPARTURE = "departure"
    ARRIVAL = "arrival"


@dataclass(order=True, frozen=True)
class SimulationEvent:
    """Represent one timestamped shipment transition in the event heap."""

    time_hours: float
    sequence: int
    shipment_id: str = field(compare=False)
    event_type: EventType = field(compare=False)
    route_index: int = field(compare=False)
