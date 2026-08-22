"""Unit tests for supply-chain API handlers."""

import pytest
from fastapi import HTTPException

from app.api import disruption as disruption_api
from app.api import network as network_api
from app.api import plan as plan_api
from app.api import scenario as scenario_api
from app.api import simulation as simulation_api
from app.domain.disruption import (
    Disruption,
    DisruptionEffects,
    DisruptionToggle,
    DisruptionType,
)
from app.domain.exposure import ExposureAnalysis
from app.domain.network import Network
from app.domain.plan import Plan, PlanAction, PlanActionType, PlanScenarioResult
from app.domain.ranking import PlanRankingResult, RankedPlan, RankingWeights
from app.domain.scenario import Scenario, ScenarioSimulationResult
from app.domain.shipment import Shipment
from app.simulation.result import SimulationResult


def test_network_handlers_return_service_results(
    monkeypatch: pytest.MonkeyPatch,
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """Network handlers return values supplied by the persistence service."""

    monkeypatch.setattr(network_api, "get_network", lambda: sample_network)
    monkeypatch.setattr(network_api, "get_shipments", lambda: [sample_shipment])

    assert network_api.network() is sample_network
    assert network_api.shipments() == [sample_shipment]


def test_disruption_handlers_persist_and_list_service_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disruption handlers delegate creation and listing to their service."""

    disruption = Disruption(
        id="port-delay",
        type=DisruptionType.PORT_CONGESTION,
        affected_node_ids=["port"],
        start_time=0,
        end_time=48,
        effects=DisruptionEffects(handling_time_multiplier=2),
    )
    monkeypatch.setattr(disruption_api, "save_disruption", lambda item: item)
    monkeypatch.setattr(disruption_api, "get_disruptions", lambda: [disruption])
    monkeypatch.setattr(
        disruption_api,
        "set_disruption_enabled",
        lambda _identifier, enabled: disruption.model_copy(update={"enabled": enabled}),
    )

    assert disruption_api.create_disruption(disruption) is disruption
    assert disruption_api.disruptions() == [disruption]
    assert disruption_api.toggle_disruption(
        disruption.id,
        DisruptionToggle(enabled=False),
    ).enabled is False


def test_disruption_toggle_returns_404_for_unknown_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Toggling an unknown disruption produces a clear HTTP 404."""

    monkeypatch.setattr(
        disruption_api,
        "set_disruption_enabled",
        lambda _identifier, _enabled: None,
    )

    with pytest.raises(HTTPException) as caught:
        disruption_api.toggle_disruption(
            "missing",
            DisruptionToggle(enabled=True),
        )

    assert caught.value.status_code == 404


def test_disruption_exposure_handler_returns_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exposure handlers analyze the requested persisted disruption."""

    disruption = Disruption(
        id="port-delay",
        type=DisruptionType.PORT_CONGESTION,
        affected_node_ids=["port"],
        start_time=0,
        end_time=48,
        effects=DisruptionEffects(handling_time_multiplier=2),
    )
    exposure = ExposureAnalysis(
        disruption_id=disruption.id,
        affected_nodes=["port", "customer"],
        affected_edges=["port-customer"],
        affected_shipments=["shipment-1"],
        affected_customers=["customer"],
    )
    monkeypatch.setattr(disruption_api, "get_disruption", lambda _identifier: disruption)
    monkeypatch.setattr(disruption_api, "analyze_exposure", lambda _item: exposure)

    assert disruption_api.disruption_exposure(disruption.id) is exposure


def test_disruption_exposure_returns_404_for_unknown_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exposure requests for unknown disruptions return HTTP 404."""

    monkeypatch.setattr(disruption_api, "get_disruption", lambda _identifier: None)

    with pytest.raises(HTTPException) as caught:
        disruption_api.disruption_exposure("missing")

    assert caught.value.status_code == 404


def test_simulation_handler_uses_persisted_network(
    monkeypatch: pytest.MonkeyPatch,
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """The simulation handler runs against persisted service values."""

    monkeypatch.setattr(simulation_api, "get_network", lambda: sample_network)
    monkeypatch.setattr(simulation_api, "get_shipments", lambda: [sample_shipment])
    monkeypatch.setattr(
        simulation_api,
        "get_disruptions",
        lambda enabled_only=False: [],
    )

    result = simulation_api.run_simulation(horizon_hours=168)

    assert result.total_cost == 2800
    assert result.average_lead_time_hours == 42
    assert result.late_shipments == 0


def test_simulation_handler_returns_422_for_invalid_state(
    monkeypatch: pytest.MonkeyPatch,
    sample_network: Network,
    sample_shipment: Shipment,
) -> None:
    """Invalid persisted simulation state is exposed as HTTP 422."""

    invalid_shipment = sample_shipment.model_copy(
        update={"route": ["supplier", "customer"]},
    )
    monkeypatch.setattr(simulation_api, "get_network", lambda: sample_network)
    monkeypatch.setattr(simulation_api, "get_shipments", lambda: [invalid_shipment])
    monkeypatch.setattr(
        simulation_api,
        "get_disruptions",
        lambda enabled_only=False: [],
    )

    with pytest.raises(HTTPException) as caught:
        simulation_api.run_simulation(horizon_hours=168)

    assert caught.value.status_code == 422
    assert "no edge" in caught.value.detail


def test_scenario_handlers_delegate_persistence_and_simulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario handlers expose create, list, single, and batch operations."""

    scenario = Scenario(
        id="scenario-a",
        name="24h closure",
        probability=0.45,
        disruptions=[],
    )
    simulation = ScenarioSimulationResult(
        scenario_id=scenario.id,
        name=scenario.name,
        probability=scenario.probability,
        total_cost=18000,
        average_lead_time_hours=54,
        delay_hours=12,
        late_shipments=0,
    )
    monkeypatch.setattr(scenario_api, "save_scenario", lambda item: item)
    monkeypatch.setattr(scenario_api, "get_scenarios", lambda: [scenario])
    monkeypatch.setattr(scenario_api, "get_scenario", lambda _identifier: scenario)
    monkeypatch.setattr(scenario_api, "simulate_scenario", lambda _item: simulation)
    monkeypatch.setattr(
        scenario_api,
        "simulate_all_scenarios",
        lambda: [simulation],
    )

    assert scenario_api.create_scenario(scenario) is scenario
    assert scenario_api.scenarios() == [scenario]
    assert scenario_api.run_scenario(scenario.id) is simulation
    assert scenario_api.simulate_all() == [simulation]


def test_scenario_simulation_returns_404_for_unknown_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulation requests for unknown scenarios return HTTP 404."""

    monkeypatch.setattr(scenario_api, "get_scenario", lambda _identifier: None)

    with pytest.raises(HTTPException) as caught:
        scenario_api.run_scenario("missing")

    assert caught.value.status_code == 404


def test_scenario_batch_returns_422_for_invalid_simulation_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid persisted simulation state is exposed as HTTP 422."""

    def fail_simulation():
        """Represent a deterministic engine validation failure."""

        raise ValueError("invalid route")

    monkeypatch.setattr(scenario_api, "simulate_all_scenarios", fail_simulation)

    with pytest.raises(HTTPException) as caught:
        scenario_api.simulate_all()

    assert caught.value.status_code == 422
    assert caught.value.detail == "invalid route"


def test_plan_handlers_delegate_persistence_and_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan handlers expose creation, listing, and matrix comparison."""

    plan = Plan(
        id="plan-1",
        name="Wait",
        actions=[PlanAction(type=PlanActionType.WAIT)],
    )
    comparison = PlanScenarioResult(
        plan_id=plan.id,
        plan_name=plan.name,
        scenario_id="scenario-a",
        scenario_name="24h closure",
        probability=0.45,
        total_cost=4640,
        average_lead_time_hours=62,
        delay_hours=20,
        late_shipments=0,
    )
    monkeypatch.setattr(plan_api, "save_plan", lambda item: item)
    monkeypatch.setattr(plan_api, "get_plans", lambda: [plan])
    monkeypatch.setattr(
        plan_api,
        "compare_plans_and_scenarios",
        lambda: [comparison],
    )

    assert plan_api.create_plan(plan) is plan
    assert plan_api.plans() == [plan]
    assert plan_api.compare() == [comparison]


def test_plan_comparison_returns_422_for_invalid_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid intervention state is exposed as HTTP 422."""

    def fail_comparison() -> None:
        """Represent an action validation failure from the engine."""

        raise ValueError("unknown shipment")

    monkeypatch.setattr(plan_api, "compare_plans_and_scenarios", fail_comparison)

    with pytest.raises(HTTPException) as caught:
        plan_api.compare()

    assert caught.value.status_code == 422
    assert caught.value.detail == "unknown shipment"


def test_plan_ranking_handler_returns_service_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan ranking delegates configurable weights to the ranking service."""

    weights = RankingWeights()
    ranked = RankedPlan(
        rank=1,
        plan_id="plan-2",
        plan_name="Reroute",
        expected_cost=5740,
        expected_delay=0,
        worst_case_cost=5740,
        score=7175,
    )
    result = PlanRankingResult(
        recommended_plan=ranked.plan_id,
        expected_cost=ranked.expected_cost,
        expected_delay=ranked.expected_delay,
        worst_case_cost=ranked.worst_case_cost,
        weights=weights,
        plans=[ranked],
    )
    monkeypatch.setattr(plan_api, "rank_plans", lambda supplied: result)

    assert plan_api.rank(weights) is result
