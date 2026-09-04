"""PostgreSQL adapter for immutable experiment packages and result copies."""
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from app.database import SessionLocal
from app.domain.repository import (ExperimentPreparation, ExperimentSignal,
    SignalRelationship, SimulationResultSnapshot)
from app.integrations.contracts import ExperimentPackage
from app.models import (ExperimentPackageRecord, SignalEffectRecord, SignalRecord,
    SignalRelationshipRecord, SignalVersionRecord, SimulationResultCopyRecord)
from app.repositories.errors import NotFoundError
from app.repositories.postgres.common import translate

def _domain(r: ExperimentPackageRecord) -> ExperimentPackage:
    return ExperimentPackage(id=r.id,name=r.name,context_version=r.context_version,
        state_version=r.state_version,signal_version_ids=r.signal_version_ids,
        disruptions=r.disruptions,occurrence_probability=r.occurrence_probability,
        provenance=r.provenance,validation_summary=r.validation_summary,
        idempotency_key=r.idempotency_key,created_at=r.created_at,
        client_run_id=r.client_run_id,status=r.status)

class PostgresExperimentRepository:
    def prepare(self, version_ids: list[str]) -> ExperimentPreparation:
        try:
            with SessionLocal() as s:
                versions=list(s.scalars(select(SignalVersionRecord).where(SignalVersionRecord.id.in_(version_ids))))
                if len(versions)!=len(version_ids): raise NotFoundError("Signal version not found")
                signals={x.id:x for x in s.scalars(select(SignalRecord).where(SignalRecord.id.in_([v.signal_id for v in versions])))}
                effects={x.signal_version_id:x for x in s.scalars(select(SignalEffectRecord).where(SignalEffectRecord.signal_version_id.in_(version_ids)))}
                rels=list(s.scalars(select(SignalRelationshipRecord).where(or_(SignalRelationshipRecord.source_signal_version_id.in_(version_ids),SignalRelationshipRecord.target_signal_version_id.in_(version_ids)))))
        except SQLAlchemyError as e: translate(e)
        by_id={v.id:v for v in versions}
        return ExperimentPreparation(tuple(ExperimentSignal(id=i,signal_id=by_id[i].signal_id,
            review_status=signals[by_id[i].signal_id].review_status,
            context_version=by_id[i].context_version,occurrence_probability=by_id[i].occurrence_probability,
            normalized_disruption=effects[i].normalized_disruption if i in effects else None) for i in version_ids),
            tuple(SignalRelationship(r.source_signal_version_id,r.target_signal_version_id,r.relationship) for r in rels))
    def create_if_absent(self, package: ExperimentPackage) -> ExperimentPackage:
        try:
            with SessionLocal.begin() as s:
                existing=s.scalar(select(ExperimentPackageRecord).where(ExperimentPackageRecord.idempotency_key==package.idempotency_key))
                if existing:return _domain(existing)
                r=ExperimentPackageRecord(id=package.id,name=package.name,context_version=package.context_version,state_version=package.state_version,signal_version_ids=package.signal_version_ids,disruptions=package.disruptions,occurrence_probability=package.occurrence_probability,provenance=package.provenance,validation_summary=package.validation_summary,idempotency_key=package.idempotency_key,client_run_id=None,status=package.status,created_at=package.created_at);s.add(r)
        except SQLAlchemyError as e: translate(e)
        return _domain(r)
    def get(self, experiment_id: str) -> ExperimentPackage | None:
        try:
            with SessionLocal() as s:r=s.get(ExperimentPackageRecord,experiment_id)
        except SQLAlchemyError as e:translate(e)
        return _domain(r) if r else None
    def mark_submitted(self, experiment_id: str, run_id: str, status: str) -> ExperimentPackage:
        try:
            with SessionLocal.begin() as s:
                r=s.get(ExperimentPackageRecord,experiment_id)
                if r is None:raise NotFoundError("Experiment not found")
                r.client_run_id=run_id;r.status=status
        except SQLAlchemyError as e:translate(e)
        return _domain(r)
    def save_result(self, experiment_id: str, result: SimulationResultSnapshot) -> None:
        try:
            with SessionLocal.begin() as s:
                if s.get(SimulationResultCopyRecord,result.run_id) is None:s.add(SimulationResultCopyRecord(run_id=result.run_id,experiment_id=experiment_id,context_version=result.context_version,state_version=result.state_version,result=result.result,completed_at=result.completed_at))
                with s.no_autoflush:
                    package=s.get(ExperimentPackageRecord,experiment_id)
                if package is None:raise NotFoundError("Experiment not found")
                package.status="COMPLETED"
        except SQLAlchemyError as e:translate(e)
    def get_result(self,run_id:str)->SimulationResultSnapshot|None:
        try:
            with SessionLocal() as s:copy=s.get(SimulationResultCopyRecord,run_id)
        except SQLAlchemyError as e:translate(e)
        return SimulationResultSnapshot(copy.run_id,copy.context_version,copy.state_version,copy.result,copy.completed_at) if copy else None
