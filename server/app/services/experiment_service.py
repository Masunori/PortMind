"""Relationship-safe immutable experiment construction and client handoff."""

from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select

from app.database import SessionLocal
from app.integrations.contracts import ExperimentPackage, SimulationSubmission
from app.integrations.gateway import ClientGateway
from app.models import (
    ExperimentPackageRecord, SignalEffectRecord, SignalRecord, SignalRelationshipRecord,
    SignalVersionRecord, SimulationResultCopyRecord,
)


def _domain(record: ExperimentPackageRecord) -> ExperimentPackage:
    return ExperimentPackage(id=record.id, name=record.name, context_version=record.context_version,
        state_version=record.state_version, signal_version_ids=record.signal_version_ids,
        disruptions=record.disruptions, occurrence_probability=record.occurrence_probability,
        provenance=record.provenance, validation_summary=record.validation_summary,
        idempotency_key=record.idempotency_key, created_at=record.created_at,
        client_run_id=record.client_run_id, status=record.status)


def _validate_relationships(version_ids: list[str], relationships: list[SignalRelationshipRecord]) -> None:
    selected = set(version_ids)
    for item in relationships:
        source_selected = item.source_signal_version_id in selected
        target_selected = item.target_signal_version_id in selected
        if item.relationship == "MUTUALLY_EXCLUSIVE" and source_selected and target_selected:
            raise ValueError("Mutually exclusive signals cannot share an experiment")
        if item.relationship == "REQUIRES" and source_selected and not target_selected:
            raise ValueError("A required signal is missing")
        if item.relationship == "SUPERSEDES" and source_selected and target_selected:
            raise ValueError("A superseded signal cannot be selected with its replacement")


async def create_experiment(name: str, signal_version_ids: list[str], *, gateway: ClientGateway,
                            idempotency_key: str | None = None) -> ExperimentPackage:
    """Freeze accepted versions and only their client-normalized disruptions."""

    if not signal_version_ids or len(set(signal_version_ids)) != len(signal_version_ids):
        raise ValueError("Signal versions must be non-empty and unique")
    context = await gateway.get_context()
    with SessionLocal() as session:
        versions = list(session.scalars(select(SignalVersionRecord).where(SignalVersionRecord.id.in_(signal_version_ids))))
        if len(versions) != len(signal_version_ids): raise LookupError("Signal version not found")
        signals = {item.id: item for item in session.scalars(select(SignalRecord).where(
            SignalRecord.id.in_([version.signal_id for version in versions])))}
        effects = {item.signal_version_id: item for item in session.scalars(select(SignalEffectRecord).where(
            SignalEffectRecord.signal_version_id.in_(signal_version_ids)))}
        relationships = list(session.scalars(select(SignalRelationshipRecord).where(
            (SignalRelationshipRecord.source_signal_version_id.in_(signal_version_ids)) |
            (SignalRelationshipRecord.target_signal_version_id.in_(signal_version_ids)))))
    _validate_relationships(signal_version_ids, relationships)
    if any(signals[v.signal_id].review_status != "ACCEPTED" for v in versions):
        raise ValueError("Only accepted signal versions may enter experiments")
    if any(v.context_version != context.context_version for v in versions):
        raise ValueError("Signal context is stale; reground and remap before submission")
    if any(v.id not in effects or effects[v.id].normalized_disruption is None for v in versions):
        raise ValueError("Every signal requires a client-normalized disruption")
    disruptions = [effects[version_id].normalized_disruption for version_id in signal_version_ids]
    probability = 1.0
    for version in versions: probability *= version.occurrence_probability
    canonical = {"context": context.context_version, "state": context.state_version,
                 "signals": signal_version_ids, "disruptions": disruptions}
    key = idempotency_key or hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    now = datetime.now(timezone.utc); experiment_id = f"experiment-{uuid4().hex}"
    with SessionLocal.begin() as session:
        existing = session.scalar(select(ExperimentPackageRecord).where(ExperimentPackageRecord.idempotency_key == key))
        if existing: return _domain(existing)
        record = ExperimentPackageRecord(id=experiment_id, name=name, context_version=context.context_version,
            state_version=context.state_version, signal_version_ids=signal_version_ids, disruptions=disruptions,
            occurrence_probability=probability, provenance={"signal_versions": signal_version_ids},
            validation_summary={"compatible": True, "relationship_count": len(relationships)},
            idempotency_key=key, client_run_id=None, status="READY", created_at=now)
        session.add(record)
    return _domain(record)


async def submit_experiment(experiment_id: str, *, gateway: ClientGateway) -> ExperimentPackage:
    with SessionLocal() as session:
        record = session.get(ExperimentPackageRecord, experiment_id)
        if record is None: raise LookupError("Experiment not found")
        package = _domain(record)
    accepted = await gateway.submit_simulation(SimulationSubmission(experiment_id=package.id,
        idempotency_key=package.idempotency_key, context_version=package.context_version,
        state_version=package.state_version, signal_version_ids=package.signal_version_ids,
        disruptions=package.disruptions, occurrence_probability=package.occurrence_probability,
        provenance=package.provenance))
    with SessionLocal.begin() as session:
        record = session.get(ExperimentPackageRecord, experiment_id)
        record.client_run_id = accepted.run_id; record.status = accepted.status
    return _domain(record)


async def refresh_results(experiment_id: str, *, gateway: ClientGateway) -> dict[str, object]:
    with SessionLocal() as session:
        package = session.get(ExperimentPackageRecord, experiment_id)
        if package is None: raise LookupError("Experiment not found")
        if not package.client_run_id: raise ValueError("Experiment has not been submitted")
        run_id = package.client_run_id
    status = await gateway.get_simulation(run_id)
    if status.status == "FAILED": raise RuntimeError(status.error_message or "Client simulation failed")
    if status.status != "COMPLETED": return status.model_dump(mode="json")
    results = await gateway.get_simulation_results(run_id,
        context_version=package.context_version, state_version=package.state_version,
        completed_at=status.updated_at)
    with SessionLocal.begin() as session:
        copy = session.get(SimulationResultCopyRecord, run_id)
        if copy is None:
            session.add(SimulationResultCopyRecord(run_id=run_id, experiment_id=experiment_id,
                context_version=results.context_version, state_version=results.state_version,
                result=results.result, completed_at=results.completed_at))
        package = session.get(ExperimentPackageRecord, experiment_id); package.status = "COMPLETED"
    return results.model_dump(mode="json")
