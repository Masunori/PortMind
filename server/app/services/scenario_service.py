"""Persist, list, and deterministically simulate scenarios."""

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.disruption import Disruption
from app.domain.network import Network
from app.domain.scenario import Scenario, ScenarioSimulationResult
from app.domain.shipment import Shipment
from app.models import ScenarioRecord
from app.services.network_service import get_network, get_shipments
from app.simulation import simulate


def _to_domain(record: ScenarioRecord) -> Scenario:
    """Convert one persisted scenario into its domain representation."""

    return Scenario(
        id=record.id,
        name=record.name,
        probability=record.probability,
        disruptions=[
            Disruption.model_validate(disruption)
            for disruption in record.disruptions
        ],
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


def _simulate_scenario(
    scenario: Scenario,
    network: Network,
    shipments: list[Shipment],
) -> ScenarioSimulationResult:
    """Simulate a scenario against a supplied immutable baseline dataset."""

    baseline = simulate(network, shipments)
    result = simulate(network, shipments, disruptions=scenario.disruptions)

    return ScenarioSimulationResult(
        scenario_id=scenario.id,
        name=scenario.name,
        probability=scenario.probability,
        total_cost=result.total_cost,
        average_lead_time_hours=result.average_lead_time_hours,
        delay_hours=max(
            0,
            result.average_lead_time_hours - baseline.average_lead_time_hours,
        ),
        late_shipments=result.late_shipments,
    )


def simulate_scenario(scenario: Scenario) -> ScenarioSimulationResult:
    """Simulate one scenario and calculate delay against baseline."""

    return _simulate_scenario(scenario, get_network(), get_shipments())


def simulate_all_scenarios() -> list[ScenarioSimulationResult]:
    """Run every persisted scenario in stable identifier order."""

    network = get_network()
    shipments = get_shipments()
    return [
        _simulate_scenario(scenario, network, shipments)
        for scenario in get_scenarios()
    ]
