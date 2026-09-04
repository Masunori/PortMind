"""Storage-neutral records exchanged with aggregate repositories."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any

@dataclass(frozen=True, slots=True)
class ExperimentSignal:
    id: str
    signal_id: str
    review_status: str
    context_version: str
    occurrence_probability: float
    normalized_disruption: dict[str, Any] | None

@dataclass(frozen=True, slots=True)
class SignalRelationship:
    source_signal_version_id: str
    target_signal_version_id: str
    relationship: str

@dataclass(frozen=True, slots=True)
class ExperimentPreparation:
    signals: tuple[ExperimentSignal, ...]
    relationships: tuple[SignalRelationship, ...]

@dataclass(frozen=True, slots=True)
class SimulationResultSnapshot:
    run_id: str
    context_version: str
    state_version: str
    result: dict[str, Any]
    completed_at: datetime

@dataclass(frozen=True, slots=True)
class RiskCandidateSnapshot:
    id: str
    classification: str
    signal_type: str
    temporal_window: dict[str, Any]
    occurrence_probability: float
    normalized_disruption: dict[str, Any]
    entity_ids: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class GroundedEntitySnapshot:
    entity_id: str
    entity_type: str
    display_name: str
