"""Shipment domain model."""

from datetime import datetime

from pydantic import BaseModel, Field


class Shipment(BaseModel):
    """Represent goods moving along an ordered network route."""

    id: str
    origin_id: str
    destination_id: str
    quantity: float = Field(gt=0)
    current_node_id: str
    route: list[str]
    expected_arrival: datetime
