"""HTTP endpoints for contingency plans and intervention comparison."""

from fastapi import APIRouter, HTTPException, status

from app.domain.plan import Plan, PlanStatus
from app.services.plan_service import (
    get_plans,
    save_plan,
    set_plan_status,
)

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.post("", response_model=Plan, status_code=status.HTTP_201_CREATED)
def create_plan(plan: Plan) -> Plan:
    """Persist a new plan or replace one with the same identifier."""
    if plan.status != PlanStatus.GENERATED:
        raise HTTPException(status_code=409,
            detail="Provider-created plans cannot set recommendation or decision status")
    return save_plan(plan)


@router.get("", response_model=list[Plan])
def plans() -> list[Plan]:
    """Return all persisted contingency plans."""

    return get_plans()




def _decide_plan(plan_id: str, status: PlanStatus) -> Plan:
    """Persist a human decision or return HTTP 404 for an unknown plan."""

    try:
        plan = set_plan_status(plan_id, status)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.post("/{plan_id}/approve", response_model=Plan)
def approve_plan(plan_id: str) -> Plan:
    """Mark a generated or recommended plan as human-approved."""

    return _decide_plan(plan_id, PlanStatus.APPROVED)


@router.post("/{plan_id}/reject", response_model=Plan)
def reject_plan(plan_id: str) -> Plan:
    """Mark a generated or recommended plan as human-rejected."""

    return _decide_plan(plan_id, PlanStatus.REJECTED)
