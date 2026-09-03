"""SQLAlchemy mappings for platform-owned persistence only."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScenarioRecord(Base):
    """Persist a platform-owned scenario definition."""

    __tablename__ = "scenarios"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    disruptions: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)


class PlanRecord(Base):
    """Persist a reviewable collection of client-agnostic actions."""

    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    actions: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="GENERATED")


class DataSourceRecord(Base):
    """Persist configuration and scheduling state for an ingestion source."""

    __tablename__ = "data_sources"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str | None] = mapped_column(String(2000))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scrape_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    scraper_type: Mapped[str | None] = mapped_column(String(50))
    scraper_config_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str] = mapped_column(String(30), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CollectionBatchRecord(Base):
    """Persist a user-labeled grouping of related collection runs."""

    __tablename__ = "collection_batches"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CollectionRunRecord(Base):
    """Persist execution state and outcome counts for one collection attempt."""

    __tablename__ = "collection_runs"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("collection_batches.id", ondelete="SET NULL"))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class EvidenceRecord(Base):
    """Persist canonical evidence, provenance, and retention state."""

    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False)
    collection_run_id: Mapped[str | None] = mapped_column(ForeignKey("collection_runs.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    structured_content: Mapped[object | None] = mapped_column(JSON)
    content_reference: Mapped[str | None] = mapped_column(String(2000))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id", ondelete="RESTRICT"))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_status: Mapped[str] = mapped_column(String(30), nullable=False)
    parser_warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    quality_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    retention_class: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceAssessmentRecord(Base):
    """Persist a versioned provider assessment and any human override."""

    __tablename__ = "evidence_assessments"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    relevance_probability: Mapped[float] = mapped_column(Float, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    entity_hints: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    provider_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    context_version: Mapped[str] = mapped_column(String(120), nullable=False)
    human_override: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignalRecord(Base):
    """Persist the mutable lifecycle pointer for a canonical signal."""

    __tablename__ = "signals"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    retry_of_signal_id: Mapped[str | None] = mapped_column(
        ForeignKey("signals.id", ondelete="RESTRICT"), index=True)
    current_version_id: Mapped[str | None] = mapped_column(String(120))
    lifecycle_status: Mapped[str] = mapped_column(String(30), nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_class: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignalVersionRecord(Base):
    """Persist one immutable interpreted and grounded signal revision."""

    __tablename__ = "signal_versions"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    classification: Mapped[str] = mapped_column(String(30), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(100), nullable=False)
    temporal_window: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    occurrence_probability: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[float] = mapped_column(Float, nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    grounding_confidence: Mapped[float | None] = mapped_column(Float)
    mapping_confidence: Mapped[float | None] = mapped_column(Float)
    processing_state: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    context_version: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignalEvidenceRecord(Base):
    """Associate immutable signal versions with their supporting evidence."""

    __tablename__ = "signal_evidence"
    signal_version_id: Mapped[str] = mapped_column(ForeignKey("signal_versions.id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id", ondelete="RESTRICT"), primary_key=True)


class SignalEntityRecord(Base):
    """Persist the resolution outcome for one entity mention in a signal."""

    __tablename__ = "signal_entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_version_id: Mapped[str] = mapped_column(ForeignKey("signal_versions.id", ondelete="CASCADE"), nullable=False)
    mention: Mapped[str] = mapped_column(String(300), nullable=False)
    is_target: Mapped[bool] = mapped_column(Boolean, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    method: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    context_version: Mapped[str] = mapped_column(String(120), nullable=False)


class SignalEffectRecord(Base):
    """Persist proposed, validated, and normalized disruption mappings."""

    __tablename__ = "signal_effects"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    signal_version_id: Mapped[str] = mapped_column(ForeignKey("signal_versions.id", ondelete="CASCADE"), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    errors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    mapping_proposal: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    local_validation: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    client_validation: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    normalized_disruption: Mapped[dict[str, object] | None] = mapped_column(JSON)
    catalog_version: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context_version: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignalRelationshipRecord(Base):
    """Persist a reviewed semantic link between two signal versions."""

    __tablename__ = "signal_relationships"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    source_signal_version_id: Mapped[str] = mapped_column(ForeignKey("signal_versions.id", ondelete="CASCADE"), nullable=False)
    target_signal_version_id: Mapped[str] = mapped_column(ForeignKey("signal_versions.id", ondelete="CASCADE"), nullable=False)
    relationship: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExperimentPackageRecord(Base):
    """Persist an immutable, reproducible simulation submission package."""

    __tablename__ = "experiment_packages"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    context_version: Mapped[str] = mapped_column(String(120), nullable=False)
    state_version: Mapped[str] = mapped_column(String(120), nullable=False)
    signal_version_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    disruptions: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    occurrence_probability: Mapped[float] = mapped_column(Float, nullable=False)
    provenance: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    validation_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    client_run_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SimulationResultCopyRecord(Base):
    """Cache authoritative client results with their exact version stamps."""

    __tablename__ = "simulation_result_copies"
    run_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiment_packages.id", ondelete="RESTRICT"), nullable=False)
    context_version: Mapped[str] = mapped_column(String(120), nullable=False)
    state_version: Mapped[str] = mapped_column(String(120), nullable=False)
    result: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlanningCycleRecord(Base):
    """Store a non-authoritative workflow snapshot and immutable client links."""

    __tablename__ = "planning_cycles"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentPromptRecord(Base):
    """Store an operator override for one agent's default system prompt."""

    __tablename__ = "agent_prompts"
    agent: Mapped[str] = mapped_column(String(30), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
