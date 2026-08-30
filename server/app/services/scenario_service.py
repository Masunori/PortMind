"""Persist and list platform-owned scenario definitions."""

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.scenario import Scenario
from app.models import ScenarioRecord


def _to_domain(record: ScenarioRecord) -> Scenario:
    """Convert one persisted scenario into its domain representation."""

    return Scenario(
        id=record.id,
        name=record.name,
        probability=record.probability,
        disruptions=record.disruptions,
    )


def save_scenario(scenario: Scenario) -> Scenario:
    """Create or replace a scenario with the same identifier."""

    with SessionLocal.begin() as session:
        record = session.merge(
            ScenarioRecord(
                id=scenario.id,
                name=scenario.name,
                probability=scenario.probability,
                disruptions=[
                    disruption.model_dump(mode="json")
                    for disruption in scenario.disruptions
                ],
            )
        )

    return _to_domain(record)


def get_scenarios() -> list[Scenario]:
    """Return all persisted scenarios in stable identifier order."""

    with SessionLocal() as session:
        records = session.scalars(
            select(ScenarioRecord).order_by(ScenarioRecord.id)
        ).all()
        return [_to_domain(record) for record in records]


def get_scenario(scenario_id: str) -> Scenario | None:
    """Return one scenario by identifier or ``None`` when absent."""

    with SessionLocal() as session:
        record = session.get(ScenarioRecord, scenario_id)
        return _to_domain(record) if record is not None else None
