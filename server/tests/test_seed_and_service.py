"""Tests for synthetic seeding and SQLAlchemy-backed network reads."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.disruption import Disruption, DisruptionEffects, DisruptionType
from app.models import (
    DisruptionRecord,
    EdgeRecord,
    NodeRecord,
    PlanRecord,
    ScenarioRecord,
    ShipmentRecord,
)
from app.seed import seed
from app.services.disruption_service import (
    get_disruption,
    get_disruptions,
    save_disruption,
    set_disruption_enabled,
)
from app.services.exposure_service import analyze_exposure
from app.services.network_service import get_network, get_shipments
from app.simulation import simulate


def record_counts(factory: sessionmaker[Session]) -> tuple[int, int, int, int, int]:
    """Return supply-chain and scenario row counts from a test session."""

    with factory() as session:
        return (
            session.scalar(select(func.count()).select_from(NodeRecord)) or 0,
            session.scalar(select(func.count()).select_from(EdgeRecord)) or 0,
            session.scalar(select(func.count()).select_from(ShipmentRecord)) or 0,
            session.scalar(select(func.count()).select_from(ScenarioRecord)) or 0,
            session.scalar(select(func.count()).select_from(PlanRecord)) or 0,
        )


def test_seed_creates_complete_supply_chain(
    test_session_factory: sessionmaker[Session],
    capsys,
) -> None:
    """Seeding creates the complete five-node synthetic network."""

    seed()

    assert record_counts(test_session_factory) == (6, 7, 2, 4, 3)
    assert (
        "Seeded 6 nodes, 7 edges, 2 shipments, 4 scenarios, and 3 plans."
        in capsys.readouterr().out
    )

    network = get_network()
    shipments = get_shipments()
    assert {node.name for node in network.nodes} == {
        "Supplier VN",
        "Hai Phong Port",
        "Ho Chi Minh Port",
        "PSA Singapore",
        "Singapore Warehouse",
        "Customer",
    }
    assert len(network.edges) == 7
    assert len(shipments) == 2
    assert shipments[0].route == [
        "supplier-vn",
        "hai-phong-port",
        "psa-singapore",
        "singapore-warehouse",
        "customer",
    ]


def test_seed_reconstructs_state_idempotently(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Repeated seeding removes mutations and restores baseline state."""

    seed()

    with test_session_factory.begin() as session:
        supplier = session.get(NodeRecord, "supplier-vn")
        assert supplier is not None
        supplier.inventory = 1
        session.add(
            NodeRecord(
                id="unexpected-node",
                name="Unexpected",
                type="test",
                inventory=0,
                capacity=0,
            )
        )

    save_disruption(
        Disruption(
            id="temporary-disruption",
            type=DisruptionType.PORT_CONGESTION,
            affected_node_ids=["hai-phong-port"],
            start_time=0,
            end_time=48,
            effects=DisruptionEffects(handling_time_multiplier=2),
        )
    )

    seed()

    assert record_counts(test_session_factory) == (6, 7, 2, 4, 3)
    with test_session_factory() as session:
        supplier = session.get(NodeRecord, "supplier-vn")
        assert supplier is not None
        assert supplier.inventory == 1200
        assert session.get(NodeRecord, "unexpected-node") is None
        assert session.scalar(select(func.count()).select_from(DisruptionRecord)) == 0


def test_network_service_returns_detached_domain_models(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Persistence services return populated, detached domain models."""

    seed()

    network = get_network()
    shipments = get_shipments()

    assert network.nodes[0].id == "customer"
    assert network.edges[0].id == "01-supplier-to-hai-phong"
    assert shipments[0].id == "shipment-001"
    assert shipments[0].quantity == 300


def test_disruption_service_upserts_and_lists_in_identifier_order(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Disruptions are persisted, replaced by ID, and returned stably."""

    later = Disruption(
        id="z-disruption",
        type=DisruptionType.EDGE_CLOSURE,
        affected_edge_ids=["edge-1"],
        start_time=0,
        end_time=12,
        effects=DisruptionEffects(edge_disabled=True),
    )
    earlier = Disruption(
        id="a-disruption",
        type=DisruptionType.PORT_CONGESTION,
        affected_node_ids=["port"],
        start_time=0,
        end_time=48,
        effects=DisruptionEffects(handling_time_multiplier=2),
    )
    save_disruption(later)
    save_disruption(earlier)
    save_disruption(earlier.model_copy(update={"end_time": 24}))

    disruptions = get_disruptions()

    assert [item.id for item in disruptions] == ["a-disruption", "z-disruption"]
    assert disruptions[0].end_time == 24

    disabled = set_disruption_enabled("a-disruption", False)
    assert disabled is not None
    assert disabled.enabled is False
    assert [item.id for item in get_disruptions(enabled_only=True)] == [
        "z-disruption"
    ]
    assert set_disruption_enabled("missing", True) is None
    assert get_disruption("a-disruption") is not None
    assert get_disruption("missing") is None


def test_seeded_port_congestion_changes_lead_time_from_42_to_78(
    test_session_factory: sessionmaker[Session],
) -> None:
    """The persisted acceptance scenario produces the exact target timings."""

    seed()
    network = get_network()
    shipments = get_shipments()
    congestion = Disruption(
        id="hai-phong-port-congestion",
        type=DisruptionType.PORT_CONGESTION,
        affected_node_ids=["hai-phong-port"],
        start_time=0,
        end_time=48,
        effects=DisruptionEffects(handling_time_multiplier=2),
    )

    baseline = simulate(network, shipments)
    disrupted = simulate(network, shipments, disruptions=[congestion])

    assert baseline.average_lead_time_hours == 42
    assert disrupted.average_lead_time_hours == 78

    exposure = analyze_exposure(congestion)
    assert exposure.affected_shipments == ["shipment-001", "shipment-002"]
    assert exposure.affected_customers == ["customer"]
