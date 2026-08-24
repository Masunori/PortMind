"""Contracts for grounded, reviewable disruption candidates."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class CandidateValidationStatus(str, Enum):
    """Represent deterministic validation state."""

    EXTRACTED = "EXTRACTED"
    VALIDATED = "VALIDATED"
    INVALID = "INVALID"


class CandidateReviewStatus(str, Enum):
    """Represent explicit operator review state."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class DisruptionCandidate(BaseModel):
    """Expose extracted facts, grounded IDs, validation, and provenance."""

    id: str
    document_id: str
    event_id: str | None
    disruption_type: str
    affected_locations: list[str]
    affected_node_ids: list[str]
    affected_edge_ids: list[str]
    start_time: float
    end_time: float
    probability: float
    severity: float
    effects: dict[str, object]
    summary: str
    extraction_confidence: float
    validation_status: CandidateValidationStatus
    validation_errors: list[str]
    review_status: CandidateReviewStatus
    confirmed_disruption_id: str | None
    run_id: str | None
    created_at: datetime
    updated_at: datetime


class CandidateUpdate(BaseModel):
    """Permit edits to every simulation-relevant candidate field."""

    disruption_type: str | None = None
    affected_locations: list[str] | None = None
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, ge=0)
    probability: float | None = None
    severity: float | None = None
    effects: dict[str, object] | None = None
    summary: str | None = None


class CandidateVersion(BaseModel):
    """Expose an immutable historical candidate snapshot."""

    version: int
    snapshot: dict[str, object]
    reason: str
    created_at: datetime


class CandidateProvenance(BaseModel):
    """Explain the currently available source-to-disruption evidence chain."""

    candidate_id: str
    source_id: str
    document_id: str
    assessment_decision: str | None
    event_id: str | None
    confirmed_disruption_id: str | None
    run_id: str | None
    version_count: int
