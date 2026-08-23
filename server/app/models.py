"""SQLAlchemy mappings for persisted supply-chain entities."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NodeRecord(Base):
    """Persist a supply-chain node in the ``nodes`` table."""

    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    inventory: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[float] = mapped_column(Float, nullable=False)


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
