"""Aggregate supply-chain network domain model."""

from pydantic import BaseModel

from app.domain.edge import Edge
from app.domain.node import Node


class Network(BaseModel):
    """Collect the nodes and directed edges forming a supply chain."""

    nodes: list[Node]
    edges: list[Edge]
