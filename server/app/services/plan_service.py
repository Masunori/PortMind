"""Persist plans and compare their actions across all scenarios."""

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.plan import Plan, PlanAction, PlanScenarioResult
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
    )


def save_plan(plan: Plan) -> Plan:
    """Create or replace a contingency plan with the same identifier."""

    with SessionLocal.begin() as session:
        record = session.merge(
            PlanRecord(
                id=plan.id,
                name=plan.name,
                actions=[action.model_dump(mode="json") for action in plan.actions],
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


def compare_plans_and_scenarios() -> list[PlanScenarioResult]:
    """Run the Cartesian product of persisted plans and scenarios."""

    network = get_network()
    shipments = get_shipments()
    baseline = simulate(network, shipments)
    results: list[PlanScenarioResult] = []

    for plan in get_plans():
        for scenario in get_scenarios():
            simulation = simulate(
                network,
                shipments,
                scenario=scenario,
                actions=plan.actions,
            )
            results.append(
                PlanScenarioResult(
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
            )
    return results
