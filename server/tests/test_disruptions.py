"""Validation and simulation tests for deterministic disruptions."""

import pytest
from pydantic import ValidationError

from app.domain.disruption import Disruption, DisruptionEffects, DisruptionType
from app.domain.network import Network
from app.domain.scenario import Scenario
from app.domain.shipment import Shipment
from app.simulation import simulate


def disruption(
    *,
    effects: DisruptionEffects,
    node_ids: list[str] | None = None,
    edge_ids: list[str] | None = None,
    end_time: float = 48,
) -> Disruption:
    """Build an active disruption for one focused engine test."""

    return Disruption(
        id="test-disruption",
        type=DisruptionType.PORT_CONGESTION,
        affected_node_ids=node_ids or [],
        affected_edge_ids=edge_ids or [],
        start_time=0,
        end_time=end_time,
        effects=effects,
    )


def test_port_congestion_changes_seed_pattern_from_42_to_78_hours(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """A 2x slowdown on a 36-hour port leg adds exactly 36 hours."""

    network = sample_network.model_copy(
        update={
            "edges": [
                sample_network.edges[0].model_copy(
                    update={"transit_time_hours": 6},
                ),
                sample_network.edges[1].model_copy(
                    update={"transit_time_hours": 36},
                ),
            ]
        },
    )

    baseline = simulate(network, [sample_shipment])
    congested = simulate(
        network,
        [sample_shipment],
        disruptions=[
            disruption(
                effects=DisruptionEffects(handling_time_multiplier=2),
                node_ids=["port"],
            )
        ],
    )

    assert baseline.average_lead_time_hours == 42
    assert congested.average_lead_time_hours == 78


def test_transit_time_multiplier_affects_targeted_edge(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """An edge transit multiplier changes only the selected leg."""

    result = simulate(
        sample_network,
        [sample_shipment],
        disruptions=[
            disruption(
                effects=DisruptionEffects(transit_time_multiplier=2),
                edge_ids=["port-customer"],
            )
        ],
    )

    assert result.average_lead_time_hours == 72


def test_node_handling_delay_is_added_at_departure(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """A fixed node handling delay extends the outbound leg."""

    result = simulate(
        sample_network,
        [sample_shipment],
        disruptions=[
            disruption(
                effects=DisruptionEffects(node_handling_delay_hours=6),
                node_ids=["port"],
            )
        ],
    )

    assert result.average_lead_time_hours == 48


@pytest.mark.parametrize(
    "effects",
    [
        DisruptionEffects(edge_disabled=True),
        DisruptionEffects(capacity_multiplier=0.25),
    ],
)
def test_blocking_effect_waits_until_disruption_ends(
    sample_network: Network,
    sample_shipment: Shipment,
    effects: DisruptionEffects,
) -> None:
    """Closures and insufficient disrupted capacity delay departure."""

    result = simulate(
        sample_network,
        [sample_shipment],
        disruptions=[
            disruption(
                effects=effects,
                edge_ids=["supplier-port"],
                end_time=10,
            )
        ],
    )

    assert result.average_lead_time_hours == 52


def test_inactive_disruption_has_no_effect(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """A disruption outside the shipment timeline leaves results unchanged."""

    inactive = Disruption(
        id="future",
        type=DisruptionType.TRANSIT_DELAY,
        affected_edge_ids=["supplier-port"],
        start_time=100,
        end_time=120,
        effects=DisruptionEffects(transit_time_multiplier=2),
    )

    assert simulate(
        sample_network,
        [sample_shipment],
        disruptions=[inactive],
    ).average_lead_time_hours == 42


def test_disabled_disruption_has_no_effect(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """A configured but disabled disruption is ignored by the engine."""

    disabled = disruption(
        effects=DisruptionEffects(transit_time_multiplier=2),
        edge_ids=["port-customer"],
    ).model_copy(update={"enabled": False})

    result = simulate(
        sample_network,
        [sample_shipment],
        disruptions=[disabled],
    )

    assert result.average_lead_time_hours == 42


def test_disruption_is_enabled_by_default() -> None:
    """New disruption configurations are active unless explicitly disabled."""

    configured = disruption(
        effects=DisruptionEffects(edge_disabled=True),
        edge_ids=["edge-1"],
    )

    assert configured.enabled is True


@pytest.mark.parametrize(
    "values",
    [
        {"affected_node_ids": [], "affected_edge_ids": []},
        {"start_time": 10, "end_time": 10},
    ],
)
def test_disruption_rejects_invalid_targets_and_windows(
    values: dict[str, object],
) -> None:
    """Disruptions require targets and an increasing time window."""

    defaults = {
        "id": "invalid",
        "type": DisruptionType.PORT_CONGESTION,
        "affected_node_ids": ["port"],
        "affected_edge_ids": [],
        "start_time": 0,
        "end_time": 10,
        "effects": DisruptionEffects(handling_time_multiplier=2),
    }
    defaults.update(values)

    with pytest.raises(ValidationError):
        Disruption(**defaults)


def test_disruption_effects_cannot_be_empty() -> None:
    """An effects object must modify at least one simulation behavior."""

    with pytest.raises(ValidationError):
        DisruptionEffects()


def test_simulation_accepts_a_scenario_directly(
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """A scenario supplies its disruption set to the engine explicitly."""

    scenario = Scenario(
        id="scenario-delay",
        name="Transit delay",
        probability=0.5,
        disruptions=[
            disruption(
                effects=DisruptionEffects(transit_time_multiplier=2),
                edge_ids=["port-customer"],
            )
        ],
    )

    result = simulate(sample_network, [sample_shipment], scenario=scenario)

    assert result.average_lead_time_hours == 72
