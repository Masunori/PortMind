"""Tests for plan persistence and plan-by-scenario comparison."""

from sqlalchemy.orm import Session, sessionmaker

from app.domain.plan import Plan, PlanAction, PlanActionType
from app.seed import seed
from app.services.plan_service import (
    compare_plans_and_scenarios,
    get_plans,
    save_plan,
)


def test_plan_service_upserts_and_lists_stably(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Plans round-trip typed inline actions and replace matching IDs."""

    later = Plan(
        id="plan-z",
        name="Wait",
        actions=[PlanAction(type=PlanActionType.WAIT)],
    )
    earlier = Plan(
        id="plan-a",
        name="Expedite",
        actions=[
            PlanAction(
                type=PlanActionType.EXPEDITE_SHIPMENT,
                shipment_id="shipment-1",
                transit_time_multiplier=0.5,
                cost_multiplier=2,
            )
        ],
    )
    save_plan(later)
    save_plan(earlier)
    save_plan(earlier.model_copy(update={"name": "Emergency expedite"}))

    plans = get_plans()

    assert [plan.id for plan in plans] == ["plan-a", "plan-z"]
    assert plans[0].name == "Emergency expedite"
    assert plans[0].actions[0].type is PlanActionType.EXPEDITE_SHIPMENT


def test_seeded_plans_compare_across_every_scenario(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Three plans by four scenarios produce twelve stable comparisons."""

    seed()

    results = compare_plans_and_scenarios()

    assert len(results) == 12
    by_plan = {
        plan_id: [result for result in results if result.plan_id == plan_id]
        for plan_id in {result.plan_id for result in results}
    }
    assert [result.average_lead_time_hours for result in by_plan["plan-1-wait"]] == [
        62,
        86,
        110,
        158,
    ]
    assert [result.delay_hours for result in by_plan["plan-1-wait"]] == [
        20,
        44,
        68,
        116,
    ]
    assert {
        (result.total_cost, result.average_lead_time_hours, result.delay_hours)
        for result in by_plan["plan-2-reroute"]
    } == {(5740, 38, 0)}
    assert {
        (result.total_cost, result.average_lead_time_hours, result.delay_hours)
        for result in by_plan["plan-3-air-freight"]
    } == {(18540, 10, 0)}
