"""Public contracts for orchestrated supply-chain response runs."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.domain.plan import Plan, PlanScenarioResult
from app.domain.ranking import PlanRankingResult
from app.domain.scenario import Scenario


class RunRequest(BaseModel):
    """Request a response workflow for one raw external signal."""

    signal: str = Field(min_length=1)


class RunStatus(str, Enum):
    """Track lifecycle state for an observable background run."""

    GENERATED = "GENERATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RunEventType(str, Enum):
    """Identify observable milestones emitted by orchestration."""

    RUN_STARTED = "RUN_STARTED"
    SIGNAL_INTERPRETED = "SIGNAL_INTERPRETED"
    ENTITIES_GROUNDED = "ENTITIES_GROUNDED"
    EXPOSURE_ANALYZED = "EXPOSURE_ANALYZED"
    SCENARIOS_GENERATED = "SCENARIOS_GENERATED"
    PLANS_GENERATED = "PLANS_GENERATED"
    SIMULATION_STARTED = "SIMULATION_STARTED"
    SIMULATION_COMPLETED = "SIMULATION_COMPLETED"
    RANKING_COMPLETED = "RANKING_COMPLETED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"


class RunEvent(BaseModel):
    """Represent one persisted observable workflow milestone."""

    sequence: int = Field(ge=1)
    type: RunEventType
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class RunResponse(BaseModel):
    """Return a completed synchronous workflow result."""

    run_id: str
    status: RunStatus
    signal: str = ""
    scenarios: list[Scenario]
    plans: list[Plan]
    results: list[PlanScenarioResult]
    recommendation: PlanRankingResult | None
    error: str | None = None
