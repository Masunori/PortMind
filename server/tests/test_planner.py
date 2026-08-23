"""Tests for deterministic planning capabilities and proposal validation."""

import asyncio

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.agents.planner import (
    ContingencyPlanner,
    PlanActionProposal,
    PlanProposal,
    PlanProposalBatch,
    PlanningContext,
    validate_and_convert_plans,
)
from app.ai import MockAIProvider
from app.domain.exposure import ExposureAnalysis
from app.domain.plan import PlanActionType
from app.seed import seed
from app.services.planning_tools import (
    get_affected_shipments,
    get_available_routes,
    get_inventory,
    get_route_capacity,
    get_transport_modes,
)


def planning_context() -> PlanningContext:
    """Build grounded exposure covering both seeded shipments."""

    return PlanningContext(
        exposure=ExposureAnalysis(
            disruption_id="weather",
            affected_nodes=["hai-phong-port"],
            affected_edges=["02-hai-phong-to-psa"],
            affected_shipments=["shipment-001", "shipment-002"],
            affected_customers=["customer"],
        )
    )


def test_planning_capabilities_read_only_persisted_state(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Planner capabilities expose shipments, routes, inventory, modes, and capacity."""

    seed()
    context = planning_context()

    assert [item.id for item in get_affected_shipments(context.exposure)] == [
        "shipment-001",
        "shipment-002",
    ]
    routes = get_available_routes("supplier-vn", "customer")
    assert [
        "supplier-vn",
        "ho-chi-minh-port",
        "psa-singapore",
        "singapore-warehouse",
        "customer",
    ] in routes
    assert get_inventory("supplier-vn") == 1200
    assert get_transport_modes() == ["air", "sea", "truck"]
    assert get_route_capacity(routes[0]) > 0


def test_mock_planner_returns_four_validated_domain_plans(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Mock plan assumptions produce wait, reroute, air, and hybrid plans."""

    seed()

    plans = asyncio.run(
        ContingencyPlanner(MockAIProvider()).generate(planning_context())
    )

    assert [plan.name for plan in plans] == [
        "Wait",
        "Reroute via Ho Chi Minh City",
        "Air-freight urgent inventory",
        "Partial air + sea",
    ]
    assert plans[0].actions[0].type is PlanActionType.WAIT
    assert len(plans[-1].actions) == 2


def test_validator_rejects_invented_route_node(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Provider-proposed graph IDs cannot bypass route validation."""

    seed()
    batch = PlanProposalBatch(
        proposals=[
            PlanProposal(
                name="Invented route",
                rationale="Invalid demo",
                actions=[
                    PlanActionProposal(
                        type=PlanActionType.REROUTE_SHIPMENT,
                        shipment_id="shipment-001",
                        new_route=["supplier-vn", "invented-port", "customer"],
                    )
                ],
            )
        ]
    )

    with pytest.raises(ValueError, match="does not exist"):
        validate_and_convert_plans(planning_context(), batch)


def test_validator_rejects_unaffected_shipment(
    test_session_factory: sessionmaker[Session],
) -> None:
    """A proposal can target only shipments proven affected by exposure."""

    seed()
    batch = PlanProposalBatch(
        proposals=[
            PlanProposal(
                name="Unknown shipment",
                rationale="Invalid demo",
                actions=[
                    PlanActionProposal(
                        type=PlanActionType.EXPEDITE_SHIPMENT,
                        shipment_id="shipment-999",
                    )
                ],
            )
        ]
    )

    with pytest.raises(ValueError, match="Unknown or unaffected shipment"):
        validate_and_convert_plans(planning_context(), batch)


def test_route_capacity_rejects_nonexistent_leg(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Capacity lookup cannot calculate a provider-invented route."""

    seed()

    with pytest.raises(ValueError, match="No route edge"):
        get_route_capacity(["supplier-vn", "customer"])
