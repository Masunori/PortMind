"""HTTP endpoints for scenario persistence and simulation."""

from fastapi import APIRouter, HTTPException, status

from app.domain.scenario import Scenario, ScenarioSimulationResult
from app.services.scenario_service import (
    get_scenario,
    get_scenarios,
    save_scenario,
    simulate_all_scenarios,
    simulate_scenario,
)

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


@router.post("", response_model=Scenario, status_code=status.HTTP_201_CREATED)
def create_scenario(scenario: Scenario) -> Scenario:
    """Persist a new scenario or replace one with the same identifier."""

    return save_scenario(scenario)


@router.get("", response_model=list[Scenario])
def scenarios() -> list[Scenario]:
    """Return all persisted scenarios."""

    return get_scenarios()


@router.post("/simulate-all", response_model=list[ScenarioSimulationResult])
def simulate_all() -> list[ScenarioSimulationResult]:
    """Run every persisted scenario in one deterministic batch."""

    try:
        return simulate_all_scenarios()
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{scenario_id}/simulate", response_model=ScenarioSimulationResult)
def run_scenario(scenario_id: str) -> ScenarioSimulationResult:
    """Run one persisted scenario by identifier."""

    scenario = get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    try:
        return simulate_scenario(scenario)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
