"""Deterministic network capabilities exposed to contingency planning."""

from collections import defaultdict

from app.domain.edge import Edge
from app.domain.exposure import ExposureAnalysis
from app.domain.network import Network
from app.domain.shipment import Shipment
from app.services.network_service import get_network, get_shipments


def get_affected_shipments(
    exposure: ExposureAnalysis,
    shipments: list[Shipment] | None = None,
) -> list[Shipment]:
    """Return persisted shipments named by a grounded exposure analysis."""

    available = shipments if shipments is not None else get_shipments()
    affected_ids = set(exposure.affected_shipments)
    return sorted(
        (shipment for shipment in available if shipment.id in affected_ids),
        key=lambda shipment: shipment.id,
    )


def get_available_routes(
    origin_id: str,
    destination_id: str,
    network: Network | None = None,
    max_hops: int = 8,
) -> list[list[str]]:
    """Enumerate simple directed routes between two persisted nodes."""

    resolved_network = network or get_network()
    node_ids = {node.id for node in resolved_network.nodes}
    if origin_id not in node_ids or destination_id not in node_ids:
        return []
    outgoing: dict[str, list[Edge]] = defaultdict(list)
    for edge in resolved_network.edges:
        outgoing[edge.source_id].append(edge)
    for edges in outgoing.values():
        edges.sort(key=lambda edge: edge.id)

    routes: list[list[str]] = []

    def visit(current: str, route: list[str]) -> None:
        """Depth-first enumerate deterministic cycle-free routes."""

        if len(route) - 1 > max_hops:
            return
        if current == destination_id:
            routes.append(route)
            return
        for edge in outgoing.get(current, []):
            if edge.target_id not in route:
                visit(edge.target_id, [*route, edge.target_id])

    visit(origin_id, [origin_id])
    return routes


def get_inventory(node_id: str, network: Network | None = None) -> float:
    """Return inventory for a persisted node or reject an unknown ID."""

    resolved_network = network or get_network()
    node = next((node for node in resolved_network.nodes if node.id == node_id), None)
    if node is None:
        raise ValueError(f"Unknown inventory node {node_id}")
    return node.inventory


def get_transport_modes(network: Network | None = None) -> list[str]:
    """Return transport modes actually available in the persisted network."""

    resolved_network = network or get_network()
    return sorted({edge.mode for edge in resolved_network.edges})


def get_route_capacity(
    route: list[str],
    network: Network | None = None,
) -> float:
    """Return bottleneck capacity for a valid persisted route."""

    if len(route) < 2:
        raise ValueError("Route must contain at least two nodes")
    resolved_network = network or get_network()
    edges = {(edge.source_id, edge.target_id): edge for edge in resolved_network.edges}
    capacities: list[float] = []
    for source_id, target_id in zip(route, route[1:]):
        edge = edges.get((source_id, target_id))
        if edge is None:
            raise ValueError(f"No route edge from {source_id} to {target_id}")
        capacities.append(edge.capacity)
    return min(capacities)
