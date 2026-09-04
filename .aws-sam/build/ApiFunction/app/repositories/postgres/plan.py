"""PostgreSQL plan repository."""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.database import SessionLocal
from app.domain.plan import Plan, PlanAction, PlanStatus
from app.models import PlanRecord
from app.repositories.contracts import Page
from app.repositories.postgres.common import decode_offset, encode_offset, translate, validate_limit

def _domain(row: PlanRecord) -> Plan:
    return Plan(id=row.id, name=row.name, actions=[PlanAction.model_validate(item) for item in row.actions], status=PlanStatus(row.status))

class PostgresPlanRepository:
    def __init__(self, session_factory=None): self.session_factory = session_factory or SessionLocal
    def save(self, plan: Plan) -> Plan:
        try:
            with self.session_factory.begin() as session: row = session.merge(PlanRecord(id=plan.id, name=plan.name, actions=[item.model_dump(mode="json") for item in plan.actions], status=plan.status.value))
        except SQLAlchemyError as error: translate(error)
        return _domain(row)
    def list(self, *, limit: int = 100, continuation_token: str | None = None) -> Page[Plan]:
        validate_limit(limit); offset = decode_offset(continuation_token)
        try:
            with self.session_factory() as session: rows = session.scalars(select(PlanRecord).order_by(PlanRecord.id).offset(offset).limit(limit + 1)).all()
        except SQLAlchemyError as error: translate(error)
        return Page(tuple(_domain(row) for row in rows[:limit]), encode_offset(offset, limit) if len(rows) > limit else None)
    def set_status(self, plan_id: str, status: PlanStatus) -> Plan | None:
        try:
            with self.session_factory.begin() as session:
                row = session.get(PlanRecord, plan_id)
                if row is None: return None
                if status in {PlanStatus.APPROVED, PlanStatus.REJECTED} and row.status != PlanStatus.RECOMMENDED.value: raise ValueError("Only a recommended plan can receive a human decision")
                row.status = status.value
        except SQLAlchemyError as error: translate(error)
        return _domain(row)
