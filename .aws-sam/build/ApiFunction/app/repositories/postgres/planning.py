"""PostgreSQL planning snapshots and bounded candidate reads."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from app.database import SessionLocal
from app.domain.plan import PlanningCycle
from app.domain.repository import GroundedEntitySnapshot, RiskCandidateSnapshot, SignalRelationship
from app.models import PlanningCycleRecord, SignalEffectRecord, SignalEntityRecord, SignalRecord, SignalRelationshipRecord, SignalVersionRecord
from app.repositories.errors import ConflictError
from app.repositories.contracts import Page
from app.repositories.postgres.common import decode_offset, encode_offset, translate, validate_limit

class PostgresPlanningCycleRepository:
    def save(self,cycle:PlanningCycle,*,expected_version:int|None=None)->PlanningCycle:
        now=datetime.now(timezone.utc)
        try:
            with SessionLocal.begin() as session:
                record=session.get(PlanningCycleRecord,cycle.id)
                if record is None:
                    if expected_version not in (None,0):raise ConflictError("planning cycle version conflict")
                    record=PlanningCycleRecord(id=cycle.id,version=0,created_at=now,updated_at=now,status=cycle.status.value,payload={});session.add(record)
                elif expected_version is not None and record.version!=expected_version:raise ConflictError("planning cycle version conflict")
                next_version=record.version+1;cycle.version=next_version;result=cycle
                record.version=next_version;record.status=result.status.value;record.payload=result.model_dump(mode="json");record.updated_at=now
        except SQLAlchemyError as error:translate(error)
        return result
    def get(self,cycle_id:str)->PlanningCycle|None:
        try:
            with SessionLocal() as session:record=session.get(PlanningCycleRecord,cycle_id)
        except SQLAlchemyError as error:translate(error)
        return PlanningCycle.model_validate(record.payload) if record else None
    def list(self,*,limit:int=100,continuation_token:str|None=None)->Page[PlanningCycle]:
        validate_limit(limit);offset=decode_offset(continuation_token)
        try:
            with SessionLocal() as session:records=session.scalars(select(PlanningCycleRecord).order_by(PlanningCycleRecord.id).offset(offset).limit(limit+1)).all()
        except SQLAlchemyError as error:translate(error)
        return Page(tuple(PlanningCycle.model_validate(item.payload) for item in records[:limit]),encode_offset(offset,limit) if len(records)>limit else None)
    def relationships(self)->list[SignalRelationship]:
        try:
            with SessionLocal() as session:rows=session.scalars(select(SignalRelationshipRecord)).all()
        except SQLAlchemyError as error:translate(error)
        return [SignalRelationship(x.source_signal_version_id,x.target_signal_version_id,x.relationship) for x in rows]
    def risk_candidates(self,context_version:str)->list[RiskCandidateSnapshot]:
        try:
            with SessionLocal() as session:
                versions=list(session.scalars(select(SignalVersionRecord).join(SignalRecord,SignalRecord.id==SignalVersionRecord.signal_id).where(SignalRecord.review_status=="ACCEPTED",SignalVersionRecord.processing_state=="READY_FOR_REVIEW",SignalVersionRecord.classification.in_(["OBSERVED","FORECAST"]),SignalVersionRecord.context_version==context_version).order_by(SignalVersionRecord.id)))
                ids=[v.id for v in versions];effects={x.signal_version_id:x for x in session.scalars(select(SignalEffectRecord).where(SignalEffectRecord.signal_version_id.in_(ids)))};entities={}
                for item in session.scalars(select(SignalEntityRecord).where(SignalEntityRecord.signal_version_id.in_(ids))):
                    if item.entity_id:entities.setdefault(item.signal_version_id,[]).append(item.entity_id)
        except SQLAlchemyError as error:translate(error)
        return [RiskCandidateSnapshot(v.id,v.classification,v.signal_type,v.temporal_window,v.occurrence_probability,effects[v.id].normalized_disruption,tuple(sorted(set(entities.get(v.id,[]))))) for v in versions if v.id in effects and effects[v.id].normalized_disruption is not None]
    def grounded_entities(self,version_ids:list[str],entity_ids:set[str],context_version:str)->list[GroundedEntitySnapshot]:
        if not version_ids or not entity_ids:return []
        try:
            with SessionLocal() as session:rows=session.scalars(select(SignalEntityRecord).where(SignalEntityRecord.entity_id.in_(entity_ids),SignalEntityRecord.signal_version_id.in_(version_ids),SignalEntityRecord.context_version==context_version)).all()
        except SQLAlchemyError as error:translate(error)
        return [GroundedEntitySnapshot(x.entity_id,x.entity_type,x.mention) for x in rows if x.entity_id and x.entity_type]
