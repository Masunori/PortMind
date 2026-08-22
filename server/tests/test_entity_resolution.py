"""Tests for deterministic grounding against persisted graph entities."""

from sqlalchemy.orm import Session, sessionmaker

from app.ai.schemas import InterpretedSignal
from app.seed import seed
from app.services.entity_resolution import (
    find_edges_by_location,
    find_nodes_by_name,
    find_shipments_using_node,
    ground_interpreted_signal,
)
from app.services.network_service import get_network, get_shipments


def weather_signal(*locations: str) -> InterpretedSignal:
    """Build an interpreted weather signal for grounding tests."""

    return InterpretedSignal(
        event_type="WEATHER_DISRUPTION",
        locations=list(locations),
        expected_duration_min_hours=48,
        expected_duration_max_hours=72,
        severity=0.7,
        confidence=0.8,
    )


def test_find_nodes_matches_human_name_without_type_suffix(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Hai Phong resolves to the persisted Hai Phong Port node."""

    seed()

    nodes = find_nodes_by_name("  HAI-PHONG  ")

    assert [node.id for node in nodes] == ["hai-phong-port"]


def test_find_edges_returns_only_persisted_incident_edges(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Location edge resolution covers inbound and outbound persisted routes."""

    seed()

    edges = find_edges_by_location("Hai Phong Port")

    assert [edge.id for edge in edges] == [
        "01-supplier-to-hai-phong",
        "02-hai-phong-to-psa",
    ]


def test_find_shipments_uses_only_explicit_routes(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Both seeded shipments explicitly traverse the grounded port node."""

    seed()

    shipments = find_shipments_using_node("hai-phong-port")

    assert [shipment.id for shipment in shipments] == [
        "shipment-001",
        "shipment-002",
    ]
    assert find_shipments_using_node("invented-node") == []


def test_ground_signal_returns_graph_ids_and_unresolved_names(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Grounding includes proven IDs and preserves names it cannot resolve."""

    seed()

    grounded = ground_interpreted_signal(
        weather_signal("Hai Phong", "Invented Atlantis Port")
    )

    assert grounded.node_ids == ["hai-phong-port"]
    assert grounded.edge_ids == [
        "01-supplier-to-hai-phong",
        "02-hai-phong-to-psa",
    ]
    assert grounded.shipment_ids == ["shipment-001", "shipment-002"]
    assert grounded.unresolved_locations == ["Invented Atlantis Port"]


def test_resolver_results_are_members_of_the_persisted_graph(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Every grounded identifier is backed by persisted domain state."""

    seed()
    network = get_network()
    shipments = get_shipments()

    grounded = ground_interpreted_signal(weather_signal("Hai Phong Port"))

    assert set(grounded.node_ids) <= {node.id for node in network.nodes}
    assert set(grounded.edge_ids) <= {edge.id for edge in network.edges}
    assert set(grounded.shipment_ids) <= {shipment.id for shipment in shipments}
