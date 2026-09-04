"""PostgreSQL scenario repository."""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.database import SessionLocal
from app.domain.scenario import Scenario
from app.models import ScenarioRecord
from app.repositories.contracts import Page
from app.repositories.postgres.common import decode_offset, encode_offset, translate, validate_limit

def _domain(row: ScenarioRecord) -> Scenario:
    return Scenario(id=row.id, name=row.name, probability=row.probability, disruptions=row.disruptions)

class PostgresScenarioRepository:
    def __init__(self, session_factory=None): self.session_factory = session_factory or SessionLocal
    def save(self, scenario: Scenario) -> Scenario:
        try:
            with self.session_factory.begin() as session:
                row = session.merge(ScenarioRecord(id=scenario.id, name=scenario.name, probability=scenario.probability,
                    disruptions=[item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in scenario.disruptions]))
        except SQLAlchemyError as error: translate(error)
        return _domain(row)
    def list(self, *, limit: int = 100, continuation_token: str | None = None) -> Page[Scenario]:
        validate_limit(limit); offset = decode_offset(continuation_token)
        try:
            with self.session_factory() as session: rows = session.scalars(select(ScenarioRecord).order_by(ScenarioRecord.id).offset(offset).limit(limit + 1)).all()
        except SQLAlchemyError as error: translate(error)
        return Page(tuple(_domain(row) for row in rows[:limit]), encode_offset(offset, limit) if len(rows) > limit else None)
    def get(self, scenario_id: str) -> Scenario | None:
        try:
            with self.session_factory() as session: row = session.get(ScenarioRecord, scenario_id)
        except SQLAlchemyError as error: translate(error)
        return _domain(row) if row else None
