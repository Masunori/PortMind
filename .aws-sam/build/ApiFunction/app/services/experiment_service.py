"""Relationship-safe immutable experiment construction and client handoff."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4
from app.domain.repository import SignalRelationship, SimulationResultSnapshot
from app.integrations.contracts import ExperimentPackage, SimulationSubmission
from app.integrations.gateway import ClientGateway
from app.repositories import get_experiment_repository
from app.repositories.contracts import ExperimentRepository
from app.repositories.errors import NotFoundError

def _repo(repository: ExperimentRepository | None = None) -> ExperimentRepository:
    return repository or get_experiment_repository()

def _validate_relationships(version_ids: list[str], relationships: list[SignalRelationship]) -> None:
    selected=set(version_ids)
    for item in relationships:
        source=item.source_signal_version_id in selected;target=item.target_signal_version_id in selected
        if item.relationship=="MUTUALLY_EXCLUSIVE" and source and target:raise ValueError("Mutually exclusive signals cannot share an experiment")
        if item.relationship=="REQUIRES" and source and not target:raise ValueError("A required signal is missing")
        if item.relationship=="SUPERSEDES" and source and target:raise ValueError("A superseded signal cannot be selected with its replacement")

async def create_experiment(name:str,signal_version_ids:list[str],*,gateway:ClientGateway,
                            idempotency_key:str|None=None,repository:ExperimentRepository|None=None)->ExperimentPackage:
    if not signal_version_ids or len(set(signal_version_ids))!=len(signal_version_ids):raise ValueError("Signal versions must be non-empty and unique")
    context=await gateway.get_context()
    try:prepared=_repo(repository).prepare(signal_version_ids)
    except NotFoundError as e:raise LookupError(str(e)) from e
    _validate_relationships(signal_version_ids,list(prepared.relationships))
    if any(x.review_status!="ACCEPTED" for x in prepared.signals):raise ValueError("Only accepted signal versions may enter experiments")
    if any(x.context_version!=context.context_version for x in prepared.signals):raise ValueError("Signal context is stale; reground and remap before submission")
    if any(x.normalized_disruption is None for x in prepared.signals):raise ValueError("Every signal requires a client-normalized disruption")
    disruptions=[x.normalized_disruption for x in prepared.signals];probability=1.0
    for item in prepared.signals:probability*=item.occurrence_probability
    canonical={"context":context.context_version,"state":context.state_version,"signals":signal_version_ids,"disruptions":disruptions}
    key=idempotency_key or hashlib.sha256(json.dumps(canonical,sort_keys=True).encode()).hexdigest()
    package=ExperimentPackage(id=f"experiment-{uuid4().hex}",name=name,context_version=context.context_version,state_version=context.state_version,signal_version_ids=signal_version_ids,disruptions=disruptions,occurrence_probability=probability,provenance={"signal_versions":signal_version_ids},validation_summary={"compatible":True,"relationship_count":len(prepared.relationships)},idempotency_key=key,client_run_id=None,status="READY",created_at=datetime.now(timezone.utc))
    return _repo(repository).create_if_absent(package)

async def submit_experiment(experiment_id:str,*,gateway:ClientGateway,repository:ExperimentRepository|None=None)->ExperimentPackage:
    repo=_repo(repository);package=repo.get(experiment_id)
    if package is None:raise LookupError("Experiment not found")
    accepted=await gateway.submit_simulation(SimulationSubmission(experiment_id=package.id,idempotency_key=package.idempotency_key,context_version=package.context_version,state_version=package.state_version,signal_version_ids=package.signal_version_ids,disruptions=package.disruptions,occurrence_probability=package.occurrence_probability,provenance=package.provenance))
    try:return repo.mark_submitted(experiment_id,accepted.run_id,accepted.status)
    except NotFoundError as e:raise LookupError(str(e)) from e

async def refresh_results(experiment_id:str,*,gateway:ClientGateway,repository:ExperimentRepository|None=None)->dict[str,object]:
    repo=_repo(repository);package=repo.get(experiment_id)
    if package is None:raise LookupError("Experiment not found")
    if not package.client_run_id:raise ValueError("Experiment has not been submitted")
    status=await gateway.get_simulation(package.client_run_id)
    if status.status=="FAILED":raise RuntimeError(status.error_message or "Client simulation failed")
    if status.status!="COMPLETED":return status.model_dump(mode="json")
    result=await gateway.get_simulation_results(package.client_run_id,context_version=package.context_version,state_version=package.state_version,completed_at=status.updated_at)
    repo.save_result(experiment_id,SimulationResultSnapshot(run_id=result.run_id,context_version=result.context_version,state_version=result.state_version,result=result.result,completed_at=result.completed_at))
    return result.model_dump(mode="json")
