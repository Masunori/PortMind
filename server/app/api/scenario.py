"""HTTP endpoints for platform-owned scenario persistence."""

from fastapi import APIRouter, status

from app.domain.scenario import Scenario
from app.services.scenario_service import (
    get_scenario,
    get_scenarios,
    save_scenario,
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
