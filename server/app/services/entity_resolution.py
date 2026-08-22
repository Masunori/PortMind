"""Resolve human-readable locations against persisted graph entities."""

import re
import unicodedata

from app.ai.schemas import InterpretedSignal
from app.domain.edge import Edge
from app.domain.grounding import GroundedSignal
from app.domain.network import Network
from app.domain.node import Node
from app.domain.shipment import Shipment
from app.services.network_service import get_network, get_shipments

GENERIC_LOCATION_WORDS = {
    "customer",
    "facility",
    "port",
    "supplier",
    "terminal",
    "warehouse",
}


def _normalize_name(value: str) -> str:
    """Normalize human-readable text for deterministic name comparison."""

    normalized = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def _matches_name(query: str, candidate: str) -> bool:
    """Return whether a meaningful location query matches a node name."""

    query_tokens = set(query.split())
    candidate_tokens = set(candidate.split())
    meaningful_query = query_tokens - GENERIC_LOCATION_WORDS
    if not meaningful_query:
        return False
    return query_tokens <= candidate_tokens or candidate_tokens <= query_tokens


def find_nodes_by_name(
    name: str,
    network: Network | None = None,
) -> list[Node]:
    """Find persisted nodes matching a normalized human-readable name."""

    resolved_network = network or get_network()
    query = _normalize_name(name)
    if not query:
        return []

    exact = [
        node for node in resolved_network.nodes
        if _normalize_name(node.name) == query
    ]
    matches = exact or [
        node
        for node in resolved_network.nodes
        if _matches_name(query, _normalize_name(node.name))
    ]
    return sorted(matches, key=lambda node: node.id)


def find_edges_by_location(
    location: str,
    network: Network | None = None,
) -> list[Edge]:
    """Find persisted edges incident to nodes matching a human location."""

    resolved_network = network or get_network()
    node_ids = {
        node.id for node in find_nodes_by_name(location, resolved_network)
    }
    return sorted(
        (
            edge
            for edge in resolved_network.edges
            if edge.source_id in node_ids or edge.target_id in node_ids
        ),
        key=lambda edge: edge.id,
    )


def find_shipments_using_node(
    node_id: str,
    shipments: list[Shipment] | None = None,
) -> list[Shipment]:
    """Find persisted shipments whose explicit route contains a grounded ID."""

    resolved_shipments = shipments if shipments is not None else get_shipments()
    return sorted(
        (shipment for shipment in resolved_shipments if node_id in shipment.route),
        key=lambda shipment: shipment.id,
    )


def ground_interpreted_signal(
    signal: InterpretedSignal,
) -> GroundedSignal:
    """Ground every interpreted location without accepting AI-supplied IDs."""

    network = get_network()
    shipments = get_shipments()
    node_ids: set[str] = set()
    edge_ids: set[str] = set()
    shipment_ids: set[str] = set()
    unresolved_locations: list[str] = []

    for location in signal.locations:
        nodes = find_nodes_by_name(location, network)
        if not nodes:
            unresolved_locations.append(location)
            continue
        node_ids.update(node.id for node in nodes)
        edge_ids.update(
            edge.id for edge in find_edges_by_location(location, network)
        )
        for node in nodes:
            shipment_ids.update(
                shipment.id
                for shipment in find_shipments_using_node(node.id, shipments)
            )

    return GroundedSignal(
        interpreted_signal=signal,
        node_ids=sorted(node_ids),
        edge_ids=sorted(edge_ids),
        shipment_ids=sorted(shipment_ids),
        unresolved_locations=unresolved_locations,
    )
