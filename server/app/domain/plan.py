"""Simulation-agnostic platform plan envelopes."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanStatus(str, Enum):
    """Represent the human decision lifecycle of a generated plan."""

    GENERATED = "GENERATED"
    RECOMMENDED = "RECOMMENDED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PlanAction(BaseModel):
    """Describe one client-agnostic action against zero or more targets."""

    model_config = ConfigDict(extra="forbid")
    type: str = Field(min_length=1, max_length=100)
    target_ids: list[str] = Field(default_factory=list, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    """Group proposed actions into a reviewable platform-owned plan."""

    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    actions: list[PlanAction]
    status: PlanStatus = PlanStatus.GENERATED


class PlanningLifecycle(str, Enum):
    """Keep provider, execution, evaluation, and decision states explicit."""

    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    EVALUATED = "EVALUATED"
    FAILED = "FAILED"
    RECOMMENDED = "RECOMMENDED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FrozenScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    proposal_id: str
    name: str
    context_version: str
    state_version: str
    disruptions: list[dict[str, Any]] = Field(min_length=1, max_length=20)
    active_disruptions: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    occurrence_probability: float = Field(ge=0, le=1)
    signal_version_ids: list[str] = Field(default_factory=list)
    provenance: dict[str, Any]


class PlanRecordView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    proposal_id: str
    name: str
    status: PlanningLifecycle
    interventions: list[dict[str, Any]] = Field(min_length=1, max_length=20)
    planner_metadata: dict[str, Any]
    rationale: str
    assumptions: list[str]
    intervention_run_id: str | None = None
    intervention_metrics: dict[str, Any] | None = None
    rank: int | None = None
    disqualification_reasons: list[str] = Field(default_factory=list)
    ranking_explanation: str | None = None


class PlanningCycle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    scenario: FrozenScenario
    generated_scenarios: list[FrozenScenario] = Field(default_factory=list, max_length=20)
    selected_disruption_ids: list[str] = Field(default_factory=list, max_length=20)
    planner_mode: str = Field(default="single", pattern=r"^(single|panel)$")
    planning_objectives: list[str] = Field(default_factory=list, max_length=50)
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    status: PlanningLifecycle
    baseline_run_id: str | None = None
    baseline_metrics: dict[str, Any] | None = None
    plans: list[PlanRecordView] = Field(default_factory=list)
    ranking_policy_version: str = "lexicographic-v1"
    error_code: str | None = None
    error_message: str | None = None
