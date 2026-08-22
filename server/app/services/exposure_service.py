"""Deterministic graph traversal for disruption exposure analysis."""

from collections import defaultdict, deque

from app.domain.disruption import Disruption
from app.domain.edge import Edge
from app.domain.exposure import ExposureAnalysis
from app.services.network_service import get_network, get_shipments


def _route_edges(route: list[str]) -> set[tuple[str, str]]:
    """Return directed node pairs traversed by one shipment route."""

    return set(zip(route, route[1:]))


def analyze_exposure(disruption: Disruption) -> ExposureAnalysis:
    """Return every network entity structurally exposed downstream."""

    network = get_network()
    shipments = get_shipments()
    edges_by_id = {edge.id: edge for edge in network.edges}
    outgoing: dict[str, list[Edge]] = defaultdict(list)
    for edge in network.edges:
        outgoing[edge.source_id].append(edge)

    affected_nodes = set(disruption.affected_node_ids)
    affected_edges = set(disruption.affected_edge_ids)
    traversal_starts = set(disruption.affected_node_ids)

    for edge_id in disruption.affected_edge_ids:
        edge = edges_by_id.get(edge_id)
        if edge is not None:
            traversal_starts.add(edge.target_id)
            affected_nodes.add(edge.target_id)

    queue = deque(sorted(traversal_starts))
    visited: set[str] = set()
    while queue:
        node_id = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)
        affected_nodes.add(node_id)

        for edge in sorted(outgoing.get(node_id, []), key=lambda item: item.id):
            affected_edges.add(edge.id)
            affected_nodes.add(edge.target_id)
            if edge.target_id not in visited:
                queue.append(edge.target_id)

    affected_edge_pairs = {
        (edge.source_id, edge.target_id)
        for edge_id in affected_edges
        if (edge := edges_by_id.get(edge_id)) is not None
    }
    affected_shipments = sorted(
        shipment.id
        for shipment in shipments
        if set(shipment.route) & affected_nodes
        or _route_edges(shipment.route) & affected_edge_pairs
    )
    customer_ids = {
        node.id
        for node in network.nodes
        if node.type.lower() == "customer"
    }

    return ExposureAnalysis(
        disruption_id=disruption.id,
        affected_nodes=sorted(affected_nodes),
        affected_edges=sorted(affected_edges),
        affected_shipments=affected_shipments,
        affected_customers=sorted(affected_nodes & customer_ids),
    )
