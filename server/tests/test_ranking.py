"""Tests for deterministic probability-weighted plan ranking."""

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.plan import PlanScenarioResult
from app.domain.ranking import RankingWeights
from app.seed import seed
from app.services import ranking_service


def test_seeded_ranking_recommends_reroute(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Default weights favor rerouting over waiting and emergency air."""

    seed()

    result = ranking_service.rank_plans(RankingWeights())

    assert result.recommended_plan == "plan-2-reroute"
    assert result.expected_cost == 5740
    assert result.expected_delay == 0
    assert result.worst_case_cost == 5740
    assert [plan.plan_id for plan in result.plans] == [
        "plan-2-reroute",
        "plan-1-wait",
        "plan-3-air-freight",
    ]
    assert [plan.rank for plan in result.plans] == [1, 2, 3]
    wait = next(plan for plan in result.plans if plan.plan_id == "plan-1-wait")
    assert wait.expected_cost == 4640
    assert wait.expected_delay == pytest.approx(40.4)
    assert wait.worst_case_cost == 4640
    assert wait.score == pytest.approx(9840)


def test_configurable_weights_can_change_recommendation(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Cost-only ranking recommends the lowest expected-cost plan."""

    seed()

    result = ranking_service.rank_plans(
        RankingWeights(cost=1, delay=0, risk=0)
    )

    assert result.recommended_plan == "plan-1-wait"


def test_ranking_rejects_probabilities_that_do_not_sum_to_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expected-value math requires a complete probability distribution."""

    comparison = PlanScenarioResult(
        plan_id="plan-1",
        plan_name="Wait",
        scenario_id="scenario-a",
        scenario_name="Partial",
        probability=0.5,
        total_cost=100,
        average_lead_time_hours=10,
        delay_hours=2,
        late_shipments=0,
    )
    monkeypatch.setattr(
        ranking_service,
        "compare_plans_and_scenarios",
        lambda: [comparison],
    )

    with pytest.raises(ValueError, match="sum to 1"):
        ranking_service.rank_plans(RankingWeights())


def test_ranking_weights_require_an_active_objective() -> None:
    """A zero-weight score is rejected because it cannot rank plans."""

    with pytest.raises(ValidationError):
        RankingWeights(cost=0, delay=0, risk=0)
