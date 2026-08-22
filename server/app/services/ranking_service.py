"""Rank contingency plans using probability-weighted deterministic math."""

from collections import defaultdict
from math import isclose

from app.domain.plan import PlanScenarioResult
from app.domain.ranking import PlanRankingResult, RankedPlan, RankingWeights
from app.services.plan_service import compare_plans_and_scenarios


def _score_plan(
    results: list[PlanScenarioResult],
    weights: RankingWeights,
) -> RankedPlan:
    """Calculate expected metrics and weighted score for one plan."""

    probability = sum(result.probability for result in results)
    if not isclose(probability, 1, rel_tol=0, abs_tol=1e-9):
        raise ValueError(
            f"Scenario probabilities for {results[0].plan_id} must sum to 1"
        )

    expected_cost = sum(
        result.probability * result.total_cost for result in results
    )
    expected_delay = sum(
        result.probability * result.delay_hours for result in results
    )
    worst_case_cost = max(result.total_cost for result in results)
    score = (
        weights.cost * expected_cost
        + weights.delay * expected_delay
        + weights.risk * worst_case_cost
    )
    return RankedPlan(
        rank=1,
        plan_id=results[0].plan_id,
        plan_name=results[0].plan_name,
        expected_cost=expected_cost,
        expected_delay=expected_delay,
        worst_case_cost=worst_case_cost,
        score=score,
    )


def rank_plans(weights: RankingWeights) -> PlanRankingResult:
    """Rank all plans by ascending weighted score and recommend the best."""

    grouped: dict[str, list[PlanScenarioResult]] = defaultdict(list)
    for result in compare_plans_and_scenarios():
        grouped[result.plan_id].append(result)
    if not grouped:
        raise ValueError("No plan comparison results are available")

    scored = sorted(
        (_score_plan(results, weights) for results in grouped.values()),
        key=lambda plan: (plan.score, plan.plan_id),
    )
    ranked = [plan.model_copy(update={"rank": index}) for index, plan in enumerate(scored, 1)]
    recommended = ranked[0]
    return PlanRankingResult(
        recommended_plan=recommended.plan_id,
        expected_cost=recommended.expected_cost,
        expected_delay=recommended.expected_delay,
        worst_case_cost=recommended.worst_case_cost,
        weights=weights,
        plans=ranked,
    )
