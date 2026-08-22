"""HTTP endpoints for contingency plans and intervention comparison."""

from fastapi import APIRouter, HTTPException, status

from app.domain.plan import Plan, PlanScenarioResult
from app.domain.ranking import PlanRankingResult, RankingWeights
from app.services.plan_service import (
    compare_plans_and_scenarios,
    get_plans,
    save_plan,
)
from app.services.ranking_service import rank_plans

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.post("", response_model=Plan, status_code=status.HTTP_201_CREATED)
def create_plan(plan: Plan) -> Plan:
    """Persist a new plan or replace one with the same identifier."""

    return save_plan(plan)


@router.get("", response_model=list[Plan])
def plans() -> list[Plan]:
    """Return all persisted contingency plans."""

    return get_plans()


@router.post("/compare", response_model=list[PlanScenarioResult])
def compare() -> list[PlanScenarioResult]:
    """Simulate every persisted plan and scenario combination."""

    try:
        return compare_plans_and_scenarios()
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/rank", response_model=PlanRankingResult)
def rank(weights: RankingWeights) -> PlanRankingResult:
    """Rank every plan using configurable deterministic objective weights."""

    try:
        return rank_plans(weights)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
