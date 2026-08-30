"""Persist platform-owned contingency plan definitions and decisions."""

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.plan import Plan, PlanAction, PlanStatus
from app.models import PlanRecord


def _to_domain(record: PlanRecord) -> Plan:
    """Convert one persisted plan into its domain representation."""

    return Plan(
        id=record.id,
        name=record.name,
        actions=[PlanAction.model_validate(action) for action in record.actions],
        status=PlanStatus(record.status),
    )


def save_plan(plan: Plan) -> Plan:
    """Create or replace a contingency plan with the same identifier."""

    with SessionLocal.begin() as session:
        record = session.merge(
            PlanRecord(
                id=plan.id,
                name=plan.name,
                actions=[action.model_dump(mode="json") for action in plan.actions],
                status=plan.status.value,
            )
        )
    return _to_domain(record)

def get_plans() -> list[Plan]:
    """Return all persisted plans in stable identifier order."""

    with SessionLocal() as session:
        records = session.scalars(
            select(PlanRecord).order_by(PlanRecord.id)
        ).all()
        return [_to_domain(record) for record in records]


def set_plan_status(plan_id: str, status: PlanStatus) -> Plan | None:
    """Persist one plan's recommendation or human-decision status."""

    with SessionLocal.begin() as session:
        record = session.get(PlanRecord, plan_id)
        if record is None:
            return None
        if status in {PlanStatus.APPROVED, PlanStatus.REJECTED} and record.status != PlanStatus.RECOMMENDED.value:
            raise ValueError("Only a recommended plan can receive a human decision")
        record.status = status.value
    return _to_domain(record)
