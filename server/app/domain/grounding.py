"""Domain contract for deterministically grounded interpreted signals."""

from pydantic import BaseModel

from app.ai.schemas import InterpretedSignal


class GroundedSignal(BaseModel):
    """Associate interpreted locations only with persisted graph entities."""

    interpreted_signal: InterpretedSignal
    node_ids: list[str]
    edge_ids: list[str]
    shipment_ids: list[str]
    unresolved_locations: list[str]
