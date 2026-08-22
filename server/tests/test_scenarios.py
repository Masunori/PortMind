"""Tests for scenario validation, persistence, and deterministic batches."""

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.disruption import Disruption, DisruptionEffects, DisruptionType
from app.domain.scenario import Scenario
from app.seed import seed
from app.services.scenario_service import (
    get_scenario,
    get_scenarios,
    save_scenario,
    simulate_all_scenarios,
    simulate_scenario,
)


def closure_scenario(identifier: str = "scenario-test") -> Scenario:
    """Build a reusable 24-hour edge-closure scenario."""

    return Scenario(
        id=identifier,
        name="24h closure",
        probability=0.45,
        disruptions=[
            Disruption(
                id="port-closure",
                type=DisruptionType.EDGE_CLOSURE,
                affected_edge_ids=["port-customer"],
                start_time=0,
                end_time=24,
                effects=DisruptionEffects(edge_disabled=True),
            )
        ],
    )


@pytest.mark.parametrize("probability", [-0.01, 1.01])
def test_scenario_rejects_invalid_probability(probability: float) -> None:
    """Scenario probability must remain within the inclusive unit interval."""

    with pytest.raises(ValidationError):
        Scenario(
            id="invalid",
            name="Invalid",
            probability=probability,
            disruptions=[],
        )


def test_scenario_service_upserts_and_lists_stably(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Scenarios round-trip inline disruptions and replace matching IDs."""

    save_scenario(closure_scenario("scenario-z"))
    save_scenario(closure_scenario("scenario-a"))
    save_scenario(
        closure_scenario("scenario-a").model_copy(update={"probability": 0.5})
    )

    scenarios = get_scenarios()

    assert [scenario.id for scenario in scenarios] == ["scenario-a", "scenario-z"]
    assert scenarios[0].probability == 0.5
    assert scenarios[0].disruptions[0].effects.edge_disabled is True
    assert get_scenario("scenario-a") is not None
    assert get_scenario("missing") is None


def test_single_scenario_reports_delay_against_baseline(
    monkeypatch: pytest.MonkeyPatch,
    sample_network,
    sample_shipment,
) -> None:
    """A closure result reports its incremental deterministic route delay."""

    from app.services import scenario_service

    monkeypatch.setattr(scenario_service, "get_network", lambda: sample_network)
    monkeypatch.setattr(
        scenario_service,
        "get_shipments",
        lambda: [sample_shipment],
    )

    result = simulate_scenario(closure_scenario())

    assert result.total_cost == 2800
    assert result.average_lead_time_hours == 54
    assert result.delay_hours == 12
    assert result.late_shipments == 0


def test_seeded_scenarios_run_as_one_deterministic_batch(
    test_session_factory: sessionmaker[Session],
) -> None:
    """The four manual scenarios produce stable, engine-derived outcomes."""

    seed()

    results = simulate_all_scenarios()

    assert [result.probability for result in results] == [0.45, 0.35, 0.15, 0.05]
    assert [result.total_cost for result in results] == [4640, 4640, 4640, 4640]
    assert [result.average_lead_time_hours for result in results] == [
        62,
        86,
        110,
        158,
    ]
    assert [result.delay_hours for result in results] == [20, 44, 68, 116]
