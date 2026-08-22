"""Structural exposure analysis result model."""

from pydantic import BaseModel


class ExposureAnalysis(BaseModel):
    """List network entities structurally downstream of a disruption."""

    disruption_id: str
    affected_nodes: list[str]
    affected_edges: list[str]
    affected_shipments: list[str]
    affected_customers: list[str]
