"""Tests for deterministic downstream exposure traversal."""

from datetime import datetime, timezone

import pytest

from app.domain.disruption import Disruption, DisruptionEffects, DisruptionType
from app.domain.edge import Edge
from app.domain.network import Network
from app.domain.node import Node
from app.domain.shipment import Shipment
from app.services import exposure_service


def port_disruption(node_id: str = "port") -> Disruption:
    """Build a port disruption targeting one node."""

    return Disruption(
        id="port-congestion",
        type=DisruptionType.PORT_CONGESTION,
        affected_node_ids=[node_id],
        start_time=0,
        end_time=48,
        effects=DisruptionEffects(handling_time_multiplier=2),
    )


def test_exposure_traverses_downstream_nodes_edges_and_shipments(
    monkeypatch: pytest.MonkeyPatch,
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """A direct node impact propagates through its downstream route."""

    monkeypatch.setattr(exposure_service, "get_network", lambda: sample_network)
    monkeypatch.setattr(exposure_service, "get_shipments", lambda: [sample_shipment])

    exposure = exposure_service.analyze_exposure(port_disruption())

    assert exposure.affected_nodes == ["customer", "port"]
    assert exposure.affected_edges == ["port-customer"]
    assert exposure.affected_shipments == ["shipment-1"]
    assert exposure.affected_customers == ["customer"]


def test_exposure_starts_at_affected_edge_target(
    monkeypatch: pytest.MonkeyPatch,
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """A direct edge impact includes that edge and traverses from its target."""

    disruption = Disruption(
        id="edge-closure",
        type=DisruptionType.EDGE_CLOSURE,
        affected_edge_ids=["supplier-port"],
        start_time=0,
        end_time=12,
        effects=DisruptionEffects(edge_disabled=True),
    )
    monkeypatch.setattr(exposure_service, "get_network", lambda: sample_network)
    monkeypatch.setattr(exposure_service, "get_shipments", lambda: [sample_shipment])

    exposure = exposure_service.analyze_exposure(disruption)

    assert exposure.affected_nodes == ["customer", "port"]
    assert exposure.affected_edges == ["port-customer", "supplier-port"]


def test_exposure_handles_branches_and_cycles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Traversal covers branches once and terminates safely on cycles."""

    network = Network(
        nodes=[
            Node(id="a", name="A", type="port", inventory=10, capacity=100),
            Node(id="b", name="B", type="warehouse", inventory=0, capacity=100),
            Node(id="c", name="C", type="customer", inventory=0, capacity=100),
            Node(id="d", name="D", type="customer", inventory=0, capacity=100),
        ],
        edges=[
            Edge(id="a-b", source_id="a", target_id="b", mode="road", transit_time_hours=1, cost=1, capacity=10),
            Edge(id="b-a", source_id="b", target_id="a", mode="road", transit_time_hours=1, cost=1, capacity=10),
            Edge(id="b-c", source_id="b", target_id="c", mode="road", transit_time_hours=1, cost=1, capacity=10),
            Edge(id="a-d", source_id="a", target_id="d", mode="road", transit_time_hours=1, cost=1, capacity=10),
        ],
    )
    shipments = [
        Shipment(
            id="s1",
            origin_id="a",
            destination_id="c",
            quantity=1,
            current_node_id="a",
            route=["a", "b", "c"],
            expected_arrival=datetime.now(timezone.utc),
        )
    ]
    monkeypatch.setattr(exposure_service, "get_network", lambda: network)
    monkeypatch.setattr(exposure_service, "get_shipments", lambda: shipments)

    exposure = exposure_service.analyze_exposure(port_disruption("a"))

    assert exposure.affected_nodes == ["a", "b", "c", "d"]
    assert exposure.affected_edges == ["a-b", "a-d", "b-a", "b-c"]
    assert exposure.affected_customers == ["c", "d"]
