"""Persist plans and compare their actions across all scenarios."""

from collections.abc import Callable

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.plan import Plan, PlanAction, PlanScenarioResult, PlanStatus
from app.domain.scenario import Scenario
from app.domain.network import Network
from app.domain.shipment import Shipment
from app.models import PlanRecord
from app.services.network_service import get_network, get_shipments
from app.services.scenario_service import get_scenarios
from app.simulation import simulate


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
        record.status = status.value
    return _to_domain(record)


def compare_plan_scenario_sets(
    plans: list[Plan],
    scenarios: list[Scenario],
    network: Network | None = None,
    shipments: list[Shipment] | None = None,
    on_result: Callable[[int, int, PlanScenarioResult], None] | None = None,
) -> list[PlanScenarioResult]:
    """Run the Cartesian product of supplied validated plans and scenarios."""

    resolved_network = network or get_network()
    resolved_shipments = shipments if shipments is not None else get_shipments()
    baseline = simulate(resolved_network, resolved_shipments)
    results: list[PlanScenarioResult] = []

    total = len(plans) * len(scenarios)
    completed = 0
    for plan in plans:
        for scenario in scenarios:
            simulation = simulate(
                resolved_network,
                resolved_shipments,
                scenario=scenario,
                actions=plan.actions,
            )
            result = PlanScenarioResult(
                plan_id=plan.id,
                plan_name=plan.name,
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                probability=scenario.probability,
                total_cost=simulation.total_cost,
                average_lead_time_hours=simulation.average_lead_time_hours,
                delay_hours=max(
                    0,
                    simulation.average_lead_time_hours
                    - baseline.average_lead_time_hours,
                ),
                late_shipments=simulation.late_shipments,
            )
            results.append(result)
            completed += 1
            if on_result is not None:
                on_result(completed, total, result)
    return results


def compare_plans_and_scenarios() -> list[PlanScenarioResult]:
    """Run the Cartesian product of persisted plans and scenarios."""

    return compare_plan_scenario_sets(get_plans(), get_scenarios())
