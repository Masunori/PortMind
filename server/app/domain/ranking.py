"""Deterministic plan-ranking inputs and result contracts."""

from pydantic import BaseModel, Field, model_validator


class RankingWeights(BaseModel):
    """Configure cost, delay, and worst-case risk contributions to score."""

    cost: float = Field(default=1, ge=0)
    delay: float = Field(default=100, ge=0)
    risk: float = Field(default=0.25, ge=0)

    @model_validator(mode="after")
    def require_positive_weight(self) -> "RankingWeights":
        """Require at least one objective to influence the ranking."""

        if self.cost == self.delay == self.risk == 0:
            raise ValueError("At least one ranking weight must be positive")
        return self


class RankedPlan(BaseModel):
    """Summarize one plan's probability-weighted performance and score."""

    rank: int = Field(ge=1)
    plan_id: str
    plan_name: str
    expected_cost: float = Field(ge=0)
    expected_delay: float = Field(ge=0)
    worst_case_cost: float = Field(ge=0)
    score: float = Field(ge=0)


class PlanRankingResult(BaseModel):
    """Return the recommended plan and complete ordered ranking."""

    recommended_plan: str
    expected_cost: float = Field(ge=0)
    expected_delay: float = Field(ge=0)
    worst_case_cost: float = Field(ge=0)
    weights: RankingWeights
    plans: list[RankedPlan]
