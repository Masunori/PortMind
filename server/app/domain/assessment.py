"""Contracts for automated relevance review and human overrides."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class RelevanceDecision(str, Enum):
    """Classify a document for downstream extraction."""

    RELEVANT = "RELEVANT"
    IRRELEVANT = "IRRELEVANT"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class DocumentAssessment(BaseModel):
    """Expose an assessment while preserving its original provider result."""

    document_id: str
    decision: RelevanceDecision
    effective_decision: RelevanceDecision
    relevance_probability: float
    rationale: str
    matched_entities: list[str]
    human_override: RelevanceDecision | None
    assessed_at: datetime
    updated_at: datetime


class AssessmentOverride(BaseModel):
    """Accept or clear a deliberate human relevance decision."""

    decision: RelevanceDecision | None
