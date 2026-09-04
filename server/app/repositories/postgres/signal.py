"""PostgreSQL adapter for signals and immutable signal versions."""
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from app.database import SessionLocal
from app.integrations.contracts import (CanonicalSignal, Evidence, EvidenceProcessingAttempt,
    FilterResult, GroundedEntity, InterpretationProposal, ProviderMetadata, TemporalWindow)
from app.models import (EvidenceAssessmentRecord, SignalEffectRecord, SignalEntityRecord,
    SignalEvidenceRecord, SignalRecord, SignalRelationshipRecord, SignalVersionRecord)
from app.repositories.errors import ConflictError, NotFoundError
from app.repositories.contracts import Page
from app.repositories.postgres.common import decode_offset, encode_offset, translate, validate_limit

def db_errors(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except SQLAlchemyError as error:translate(error)
    return wrapped

class PostgresSignalRepository:
    @db_errors
    def attempts(self,evidence_id:str)->tuple[EvidenceProcessingAttempt,...]:
        with SessionLocal() as session:
            rows=session.execute(select(SignalRecord,SignalVersionRecord).join(SignalVersionRecord,SignalVersionRecord.signal_id==SignalRecord.id).join(SignalEvidenceRecord,SignalEvidenceRecord.signal_version_id==SignalVersionRecord.id).where(SignalEvidenceRecord.evidence_id==evidence_id,SignalRecord.current_version_id==SignalVersionRecord.id).order_by(SignalRecord.created_at,SignalRecord.id)).all()
        return tuple(EvidenceProcessingAttempt(signal_id=s.id,signal_version_id=v.id,signal_type=v.signal_type,retry_of_signal_id=s.retry_of_signal_id,review_status=s.review_status,processing_state=v.processing_state,created_at=s.created_at) for s,v in rows)
    @db_errors
    def save_assessment(self,evidence_id:str,result:FilterResult,context_version:str)->None:
        with SessionLocal.begin() as session:session.add(EvidenceAssessmentRecord(id=f"assessment-{uuid4().hex}",evidence_id=evidence_id,decision=result.decision.value,relevance_probability=result.relevance_probability,reason_codes=result.reason_codes,rationale=result.rationale,entity_hints=result.entity_hints,provider_metadata=result.metadata.model_dump(mode="json"),context_version=context_version,human_override=None,created_at=datetime.now(timezone.utc)))
    @db_errors
    def create_candidate(self,evidence:Evidence,proposal:InterpretationProposal,context_version:str,retry_of_signal_id:str|None)->str:
        now=datetime.now(timezone.utc);signal_id=f"signal-{uuid4().hex}";version_id=f"{signal_id}-v1"
        with SessionLocal.begin() as session:
            session.add(SignalRecord(id=signal_id,revision=0,retry_of_signal_id=retry_of_signal_id,current_version_id=version_id,lifecycle_status="CANDIDATE",review_status="PENDING",expires_at=None,retention_class=evidence.retention_class.value,created_at=now));session.flush()
            session.add(SignalVersionRecord(id=version_id,signal_id=signal_id,version=1,classification=proposal.classification.value,signal_type=proposal.signal_type,temporal_window=proposal.temporal_window.model_dump(mode="json"),occurrence_probability=proposal.occurrence_probability,severity=proposal.severity,extraction_confidence=proposal.extraction_confidence,grounding_confidence=None,mapping_confidence=None,processing_state="INTERPRETED",provider_metadata=proposal.metadata.model_dump(mode="json"),context_version=context_version,created_at=now));session.flush()
            for evidence_id in proposal.supporting_evidence_ids:session.add(SignalEvidenceRecord(signal_version_id=version_id,evidence_id=evidence_id))
        return version_id
    @db_errors
    def add_entity(self,version_id:str,item:GroundedEntity)->None:
        with SessionLocal.begin() as session:session.add(SignalEntityRecord(signal_version_id=version_id,mention=item.mention,is_target=item.is_target,entity_id=item.entity_id,entity_type=item.entity_type,status=item.status,method=item.method,confidence=item.confidence,context_version=item.context_version))
    @db_errors
    def add_effect(self,version_id:str,*,outcome:str,errors:list[str],mapping_proposal:dict[str,object],local_validation:dict[str,object],client_validation:dict[str,object],normalized_disruption:dict[str,object]|None,catalog_version:str,schema_hash:str,context_version:str)->None:
        with SessionLocal.begin() as session:session.add(SignalEffectRecord(id=f"effect-{uuid4().hex}",signal_version_id=version_id,outcome=outcome,errors=errors,mapping_proposal=mapping_proposal,local_validation=local_validation,client_validation=client_validation,normalized_disruption=normalized_disruption,catalog_version=catalog_version,schema_hash=schema_hash,context_version=context_version,created_at=datetime.now(timezone.utc)))
    @db_errors
    def set_processing_state(self,version_id:str,state:str)->None:
        with SessionLocal.begin() as session:
            version=session.get(SignalVersionRecord,version_id)
            if version is None:raise NotFoundError("Signal version not found")
            version.processing_state=state
    @db_errors
    def finalize(self,version_id:str,grounding_confidence:float,mapping_confidence:float|None)->CanonicalSignal:
        with SessionLocal.begin() as session:
            version=session.get(SignalVersionRecord,version_id)
            if version is None:raise NotFoundError("Signal version not found")
            version.grounding_confidence=grounding_confidence;version.mapping_confidence=mapping_confidence
            effect=session.scalar(select(SignalEffectRecord).where(SignalEffectRecord.signal_version_id==version_id).order_by(SignalEffectRecord.created_at.desc()))
            version.processing_state="READY_FOR_REVIEW" if effect and effect.outcome=="MAPPED" else ("NEEDS_RESOLUTION" if effect and effect.outcome in {"NO_ENTITIES","UNRESOLVED_ENTITIES"} else "MAPPING_FAILED")
        return self.get_version(version_id)
    @db_errors
    def get_version(self,version_id:str)->CanonicalSignal:
        with SessionLocal() as session:
            version=session.get(SignalVersionRecord,version_id)
            if version is None:raise NotFoundError("Signal version not found")
            signal=session.get(SignalRecord,version.signal_id)
            evidence_ids=list(session.scalars(select(SignalEvidenceRecord.evidence_id).where(SignalEvidenceRecord.signal_version_id==version_id)))
            entities=session.scalars(select(SignalEntityRecord).where(SignalEntityRecord.signal_version_id==version_id).order_by(SignalEntityRecord.id)).all()
            effect=session.scalar(select(SignalEffectRecord).where(SignalEffectRecord.signal_version_id==version_id).order_by(SignalEffectRecord.created_at.desc()))
        return CanonicalSignal(id=version.id,signal_id=version.signal_id,aggregate_version=signal.revision,retry_of_signal_id=signal.retry_of_signal_id,version=version.version,classification=version.classification,signal_type=version.signal_type,temporal_window=TemporalWindow.model_validate(version.temporal_window),occurrence_probability=version.occurrence_probability,severity=version.severity,extraction_confidence=version.extraction_confidence,grounding_confidence=version.grounding_confidence,mapping_confidence=version.mapping_confidence,evidence_ids=evidence_ids,entities=[GroundedEntity(mention=e.mention,is_target=e.is_target,status=e.status,entity_id=e.entity_id,entity_type=e.entity_type,method=e.method,confidence=e.confidence,context_version=e.context_version) for e in entities],provider_metadata=ProviderMetadata.model_validate(version.provider_metadata),context_version=version.context_version,lifecycle_status=signal.lifecycle_status,review_status=signal.review_status,processing_state=version.processing_state,mapping_outcome=effect.outcome if effect else None,mapping_errors=effect.errors if effect else [],mapping_proposal=effect.mapping_proposal if effect else None,local_validation=effect.local_validation if effect else None,client_validation=effect.client_validation if effect else None,normalized_disruption=effect.normalized_disruption if effect else None,catalog_version=effect.catalog_version if effect else None,schema_hash=effect.schema_hash if effect else None)
    @db_errors
    def list(self,*,review_status:str|None=None,limit:int=50,continuation_token:str|None=None)->Page[CanonicalSignal]:
        validate_limit(limit);offset=decode_offset(continuation_token)
        with SessionLocal() as session:
            query=select(SignalRecord).order_by(SignalRecord.created_at.desc())
            if review_status is not None:query=query.where(SignalRecord.review_status==review_status)
            ids=[row.current_version_id for row in session.scalars(query.limit(limit+1).offset(offset))]
        return Page(tuple(self.get_version(item) for item in ids[:limit]),encode_offset(offset,limit) if len(ids)>limit else None)
    @db_errors
    def review(self,signal_id:str,decision:str,*,expected_version:int|None=None)->CanonicalSignal:
        with SessionLocal.begin() as session:
            signal=session.get(SignalRecord,signal_id)
            if signal is None:raise NotFoundError("Signal not found")
            if expected_version is not None and signal.revision!=expected_version:raise ConflictError("signal version conflict")
            if decision=="ACCEPTED":
                effect=session.scalar(select(SignalEffectRecord).where(SignalEffectRecord.signal_version_id==signal.current_version_id));entities=session.scalars(select(SignalEntityRecord).where(SignalEntityRecord.signal_version_id==signal.current_version_id)).all()
                if any(item.status!="RESOLVED" for item in entities):raise ValueError("All entities must be resolved")
                if effect is None or effect.normalized_disruption is None:raise ValueError("Client-normalized disruption is required")
            current=signal.revision
            result=session.execute(update(SignalRecord).where(SignalRecord.id==signal_id,SignalRecord.revision==current).values(review_status=decision,lifecycle_status="ACTIVE" if decision=="ACCEPTED" else "REJECTED",revision=current+1))
            if result.rowcount!=1:raise ConflictError("signal version conflict")
            version_id=signal.current_version_id
        return self.get_version(version_id)
    @db_errors
    def relate(self,source_version_id:str,target_version_id:str,*,relationship:str,confidence:float,rationale:str)->dict[str,object]:
        relationship_id=f"relationship-{uuid4().hex}"
        with SessionLocal.begin() as session:session.add(SignalRelationshipRecord(id=relationship_id,source_signal_version_id=source_version_id,target_signal_version_id=target_version_id,relationship=relationship,confidence=confidence,rationale=rationale,created_at=datetime.now(timezone.utc)))
        return {"id":relationship_id,"relationship":relationship,"confidence":confidence,"rationale":rationale}
