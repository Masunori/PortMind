"""SQLAlchemy mappings for persisted supply-chain entities."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EntitySchemaRecord(Base):
    """Persist a named node or edge schema."""

    __tablename__ = "entity_schemas"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchemaVersionRecord(Base):
    """Persist one immutable schema definition version."""

    __tablename__ = "schema_versions"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    schema_id: Mapped[str] = mapped_column(
        ForeignKey("entity_schemas.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    fields: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SimulationRuleRecord(Base):
    """Persist a validated declarative lifecycle rule."""

    __tablename__ = "simulation_rules"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    target_metric: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NetworkContextStateRecord(Base):
    """Persist a monotonically increasing AI-context version."""

    __tablename__ = "network_context_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NodeRecord(Base):
    """Persist a supply-chain node in the ``nodes`` table."""

    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    inventory: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[float] = mapped_column(Float, nullable=False)
    schema_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("schema_versions.id", ondelete="RESTRICT")
    )
    attributes: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)


class EdgeRecord(Base):
    """Persist a directed transport edge in the ``edges`` table."""

    __tablename__ = "edges"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id"),
        nullable=False,
    )
    target_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id"),
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(50), nullable=False)
    transit_time_hours: Mapped[float] = mapped_column(Float, nullable=False)
    cost: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[float] = mapped_column(Float, nullable=False)
    schema_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("schema_versions.id", ondelete="RESTRICT")
    )
    attributes: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)


class ShipmentRecord(Base):
    """Persist a routed shipment in the ``shipments`` table."""

    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    origin_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id"),
        nullable=False,
    )
    destination_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id"),
        nullable=False,
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    current_node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id"),
        nullable=False,
    )
    route: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expected_arrival: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class DisruptionRecord(Base):
    """Persist a time-bounded disruption in the ``disruptions`` table."""

    __tablename__ = "disruptions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    affected_node_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    affected_edge_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    effects: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class ScenarioRecord(Base):
    """Persist a weighted scenario in the ``scenarios`` table."""

    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    disruptions: Mapped[list[dict[str, object]]] = mapped_column(
        JSON,
        nullable=False,
    )


class PlanRecord(Base):
    """Persist a contingency plan with inline actions."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    actions: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="GENERATED",
    )


class RunRecord(Base):
    """Persist an observable orchestration run and its final output."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    signal: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    scenarios: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    plans: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    results: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    recommendation: Mapped[dict[str, object] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RunEventRecord(Base):
    """Persist one ordered orchestration event for a run."""

    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataSourceRecord(Base):
    """Persist a user-managed ingestion source."""

    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str | None] = mapped_column(String(2000))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scrape_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    scraper_type: Mapped[str | None] = mapped_column(String(50))
    scraper_config_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str] = mapped_column(String(30), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RawDocumentRecord(Base):
    """Persist normalized content collected from a configured source."""

    __tablename__ = "raw_documents"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    media_type: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentAssessmentRecord(Base):
    """Persist provider relevance plus any explicit human override."""

    __tablename__ = "document_assessments"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("raw_documents.id", ondelete="CASCADE"), primary_key=True
    )
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    relevance_probability: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    matched_entities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    human_override: Mapped[str | None] = mapped_column(String(30))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EntityAliasRecord(Base):
    """Map normalized human aliases onto authoritative graph identifiers."""

    __tablename__ = "entity_aliases"

    alias: Mapped[str] = mapped_column(String(300), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IntelligenceEventRecord(Base):
    """Group independently sourced documents describing the same event."""

    __tablename__ = "intelligence_events"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    disruption_type: Mapped[str] = mapped_column(String(50), nullable=False)
    affected_entity_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EventDocumentRecord(Base):
    """Link one event to every independent supporting document."""

    __tablename__ = "event_documents"

    event_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_events.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("raw_documents.id", ondelete="CASCADE"), primary_key=True
    )
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DisruptionCandidateRecord(Base):
    """Persist editable, validated extraction without mutating disruptions."""

    __tablename__ = "disruption_candidates"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("raw_documents.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("intelligence_events.id", ondelete="SET NULL")
    )
    disruption_type: Mapped[str] = mapped_column(String(50), nullable=False)
    affected_locations: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    affected_node_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    affected_edge_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[float] = mapped_column(Float, nullable=False)
    effects_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    validation_errors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False)
    confirmed_disruption_id: Mapped[str | None] = mapped_column(
        ForeignKey("disruptions.id", ondelete="SET NULL")
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CandidateVersionRecord(Base):
    """Preserve every pre-edit candidate snapshot."""

    __tablename__ = "candidate_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("disruption_candidates.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
