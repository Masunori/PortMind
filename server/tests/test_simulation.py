"""Behavioral and validation tests for the deterministic engine."""

import pytest

from app.domain.edge import Edge
from app.domain.network import Network
from app.domain.plan import PlanAction, PlanActionType
from app.domain.shipment import Shipment
from app.simulation import simulate


def test_simulation_traverses_route_and_accumulates_results(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """A shipment completes its route with deterministic costs and timing."""

    result = simulate(sample_network, [sample_shipment])

    assert result.total_cost == 2800
    assert result.average_lead_time_hours == 42
    assert result.average_delay_hours == 0
    assert result.late_shipments == 0
    assert result.final_inventory == {
        "supplier": 300,
        "port": 100,
        "customer": 200,
    }


def test_simulation_marks_shipments_outside_horizon_as_late(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """A route longer than the horizon remains in transit and is late."""

    result = simulate(sample_network, [sample_shipment], horizon_hours=40)

    assert result.total_cost == 2800
    assert result.average_lead_time_hours == 42
    assert result.average_delay_hours == 2
    assert result.late_shipments == 1
    assert result.final_inventory["supplier"] == 300
    assert result.final_inventory["customer"] == 0


def test_simulation_with_no_shipments_preserves_inventory(
    sample_network: Network,
) -> None:
    """An empty workload leaves all inventory and metrics unchanged."""

    result = simulate(sample_network, [])

    assert result.total_cost == 0
    assert result.average_lead_time_hours == 0
    assert result.average_delay_hours == 0
    assert result.late_shipments == 0
    assert result.final_inventory == {
        node.id: node.inventory
        for node in sample_network.nodes
    }


@pytest.mark.parametrize(
    ("horizon", "message"),
    [
        (0, "horizon"),
        (-1, "horizon"),
    ],
)
def test_simulation_rejects_invalid_horizon(
    sample_network: Network,
    sample_shipment: Shipment,
    horizon: float,
    message: str,
) -> None:
    """Non-positive horizons are rejected before scheduling events."""

    with pytest.raises(ValueError, match=message):
        simulate(sample_network, [sample_shipment], horizon_hours=horizon)


def test_simulation_rejects_duplicate_shipment_ids(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """Duplicate shipment identifiers cannot share simulation state."""

    duplicate = sample_shipment.model_copy()

    with pytest.raises(ValueError, match="unique"):
        simulate(sample_network, [sample_shipment, duplicate])


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"route": ["supplier"]}, "at least two"),
        ({"route": ["port", "customer"]}, "start"),
        ({"route": ["supplier", "port"]}, "end"),
        ({"route": ["supplier", "missing", "customer"]}, "unknown nodes"),
        ({"route": ["supplier", "customer"]}, "no edge"),
        ({"quantity": 501}, "exceeds origin inventory"),
    ],
)
def test_simulation_rejects_invalid_shipments(
    sample_network: Network,
    sample_shipment: Shipment,
    updates: dict[str, object],
    message: str,
) -> None:
    """Malformed routes and infeasible quantities are rejected."""

    shipment = sample_shipment.model_copy(update=updates)

    with pytest.raises(ValueError, match=message):
        simulate(sample_network, [shipment])


def test_simulation_handles_multiple_shipments_in_event_order(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """Multiple shipments remain deterministic when event times coincide."""

    second = sample_shipment.model_copy(
        update={"id": "shipment-2", "quantity": 100},
    )

    result = simulate(sample_network, [sample_shipment, second])

    assert result.total_cost == 5600
    assert result.average_lead_time_hours == 42
    assert result.late_shipments == 0
    assert result.final_inventory["supplier"] == 200
    assert result.final_inventory["customer"] == 300


def test_reroute_action_uses_the_requested_network_path(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """Rerouting changes deterministic route timing and cost."""

    network = sample_network.model_copy(
        update={
            "edges": [
                *sample_network.edges,
                Edge(
                    id="supplier-customer",
                    source_id="supplier",
                    target_id="customer",
                    mode="air",
                    transit_time_hours=10,
                    cost=5000,
                    capacity=500,
                ),
            ]
        }
    )
    action = PlanAction(
        type=PlanActionType.REROUTE_SHIPMENT,
        shipment_id=sample_shipment.id,
        new_route=["supplier", "customer"],
    )

    result = simulate(network, [sample_shipment], actions=[action])

    assert result.average_lead_time_hours == 10
    assert result.total_cost == 5000


def test_expedite_action_applies_time_and_cost_multipliers(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """Expediting trades higher route cost for shorter transit time."""

    action = PlanAction(
        type=PlanActionType.EXPEDITE_SHIPMENT,
        shipment_id=sample_shipment.id,
        transit_time_multiplier=0.5,
        cost_multiplier=2,
    )

    result = simulate(sample_network, [sample_shipment], actions=[action])

    assert result.average_lead_time_hours == 21
    assert result.total_cost == 5600


def test_alternative_inventory_changes_shipment_origin(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """Alternative inventory fulfills a shipment from the selected route origin."""

    nodes = [
        node.model_copy(update={"inventory": 500}) if node.id == "port" else node
        for node in sample_network.nodes
    ]
    network = sample_network.model_copy(update={"nodes": nodes})
    action = PlanAction(
        type=PlanActionType.USE_ALTERNATIVE_INVENTORY,
        shipment_id=sample_shipment.id,
        alternative_inventory_node_id="port",
        new_route=["port", "customer"],
    )

    result = simulate(network, [sample_shipment], actions=[action])

    assert result.average_lead_time_hours == 30
    assert result.final_inventory["supplier"] == 500
    assert result.final_inventory["port"] == 300


def test_action_rejects_unknown_shipment(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """Actions cannot silently target a shipment outside the workload."""

    action = PlanAction(
        type=PlanActionType.EXPEDITE_SHIPMENT,
        shipment_id="missing",
    )

    with pytest.raises(ValueError, match="unknown shipment"):
        simulate(sample_network, [sample_shipment], actions=[action])
