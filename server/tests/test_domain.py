"""Validation tests for supply-chain domain models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domain.edge import Edge
from app.domain.node import Node
from app.domain.plan import PlanAction, PlanActionType
from app.domain.shipment import Shipment


@pytest.mark.parametrize("field", ["inventory", "capacity"])
def test_node_rejects_negative_quantities(field: str) -> None:
    """Nodes must not accept negative inventory or capacity."""

    values = {
        "id": "node-1",
        "name": "Node",
        "type": "warehouse",
        "inventory": 10,
        "capacity": 20,
    }
    values[field] = -1

    with pytest.raises(ValidationError):
        Node(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("transit_time_hours", 0),
        ("cost", -1),
        ("capacity", -1),
    ],
)
def test_edge_rejects_invalid_values(field: str, value: float) -> None:
    """Edges must reject invalid timing, cost, and capacity values."""

    values = {
        "id": "edge-1",
        "source_id": "source",
        "target_id": "target",
        "mode": "sea",
        "transit_time_hours": 12,
        "cost": 100,
        "capacity": 500,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        Edge(**values)


def test_shipment_rejects_non_positive_quantity() -> None:
    """Shipments must carry a strictly positive quantity."""

    with pytest.raises(ValidationError):
        Shipment(
            id="shipment-1",
            origin_id="source",
            destination_id="target",
            quantity=0,
            current_node_id="source",
            route=["source", "target"],
            expected_arrival=datetime.now(timezone.utc),
        )


@pytest.mark.parametrize(
    ("action_type", "values"),
    [
        (PlanActionType.REROUTE_SHIPMENT, {"shipment_id": "s1"}),
        (PlanActionType.EXPEDITE_SHIPMENT, {}),
        (
            PlanActionType.USE_ALTERNATIVE_INVENTORY,
            {"shipment_id": "s1", "new_route": ["warehouse", "customer"]},
        ),
    ],
)
def test_plan_actions_require_type_specific_fields(
    action_type: PlanActionType,
    values: dict[str, object],
) -> None:
    """Operational actions reject incomplete intervention definitions."""

    with pytest.raises(ValidationError):
        PlanAction(type=action_type, **values)
