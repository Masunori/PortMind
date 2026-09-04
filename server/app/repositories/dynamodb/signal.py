"""DynamoDB signal aggregate and immutable-history adapter."""
from __future__ import annotations
from datetime import datetime,timezone
from uuid import uuid4
from boto3.dynamodb.conditions import Attr,Key
from botocore.exceptions import BotoCoreError,ClientError
from app.integrations.contracts import (CanonicalSignal,Evidence,EvidenceProcessingAttempt,FilterResult,GroundedEntity,InterpretationProposal,SignalProcessingState)
from app.repositories.contracts import Page
from app.repositories.dynamodb.codec import decode_value,encode_value
from app.repositories.dynamodb.common import DynamoRepository,model_payload,parse_model
from app.repositories.dynamodb.operations import raise_persistence_error,transact_write,wire_item
from app.repositories.errors import ConflictError,NotFoundError

class DynamoSignalRepository(DynamoRepository):
    @staticmethod
    def _changed(value:CanonicalSignal,**changes)->CanonicalSignal:
        return CanonicalSignal.model_validate({**value.model_dump(mode="python"),**changes})
    def _version_row(self,version_id:str):
        lookup=self._get(f"SIGNAL_VERSION#{version_id}")
        if not lookup:raise NotFoundError("Signal version not found")
        row=self._get(lookup["signal_pk"],lookup["signal_sk"])
        if not row:raise NotFoundError("Signal version not found")
        return row
    def get_version(self,version_id:str)->CanonicalSignal:return parse_model(CanonicalSignal,self._version_row(version_id)["payload"])
    def _save_version(self,value:CanonicalSignal)->None:
        row=self._version_row(value.id)
        state=getattr(value.processing_state,"value",value.processing_state)
        try:self.table.put_item(Item={**row,"payload":model_payload(value),"processing_state":state})
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
    def attempts(self,evidence_id:str)->tuple[EvidenceProcessingAttempt,...]:
        try:rows=self.table.query(KeyConditionExpression=Key("PK").eq(f"EVIDENCE_SIGNAL#{evidence_id}"))["Items"]
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
        return tuple(parse_model(EvidenceProcessingAttempt,x["payload"]) for x in rows)
    def save_assessment(self,evidence_id:str,result:FilterResult,context_version:str)->None:
        now=datetime.now(timezone.utc);identifier=f"assessment-{uuid4().hex}"
        item={"PK":f"EVIDENCE#{evidence_id}","SK":f"ASSESSMENT#{encode_value(now)}#{identifier}","payload":encode_value({**result.model_dump(mode="python"),"context_version":context_version,"created_at":now})}
        try:self.table.put_item(Item=item)
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
    def create_candidate(self,evidence:Evidence,proposal:InterpretationProposal,context_version:str,retry_of_signal_id:str|None)->str:
        now=datetime.now(timezone.utc);signal_id=f"signal-{uuid4().hex}";version_id=f"{signal_id}-v1"
        value=CanonicalSignal(id=version_id,signal_id=signal_id,aggregate_version=0,retry_of_signal_id=retry_of_signal_id,version=1,classification=proposal.classification,signal_type=proposal.signal_type,temporal_window=proposal.temporal_window,occurrence_probability=proposal.occurrence_probability,severity=proposal.severity,extraction_confidence=proposal.extraction_confidence,grounding_confidence=None,mapping_confidence=None,evidence_ids=proposal.supporting_evidence_ids,entities=[],provider_metadata=proposal.metadata,context_version=context_version,lifecycle_status="CANDIDATE",review_status="PENDING",processing_state="INTERPRETED")
        attempt=EvidenceProcessingAttempt(signal_id=signal_id,signal_version_id=version_id,signal_type=proposal.signal_type,retry_of_signal_id=retry_of_signal_id,review_status="PENDING",processing_state="INTERPRETED",created_at=now)
        name=self.table.name;items=[
            {"Put":{"TableName":name,"Item":wire_item({"PK":f"SIGNAL#{signal_id}","SK":"META","version":0,"current_version_id":version_id,"GSI1PK":"SIGNAL","GSI1SK":f"{encode_value(now)}#{signal_id}","review_status":"PENDING"}),"ConditionExpression":"attribute_not_exists(PK)"}},
            {"Put":{"TableName":name,"Item":wire_item({"PK":f"SIGNAL#{signal_id}","SK":"VERSION#000001","GSI2PK":f"SIGNAL_VERSION#{version_id}","GSI2SK":"META","payload":model_payload(value),"processing_state":"INTERPRETED"}),"ConditionExpression":"attribute_not_exists(PK)"}},
            {"Put":{"TableName":name,"Item":wire_item({"PK":f"SIGNAL_VERSION#{version_id}","SK":"META","signal_pk":f"SIGNAL#{signal_id}","signal_sk":"VERSION#000001"}),"ConditionExpression":"attribute_not_exists(PK)"}},
            *({"Put":{"TableName":name,"Item":wire_item({"PK":f"EVIDENCE_SIGNAL#{item_id}","SK":f"SIGNAL#{signal_id}","payload":model_payload(attempt)})}} for item_id in proposal.supporting_evidence_ids),
        ];transact_write(self.table.meta.client,items)
        return version_id
    def add_entity(self,version_id:str,item:GroundedEntity)->None:
        value=self.get_version(version_id);self._save_version(self._changed(value,entities=[*value.entities,item]))
    def add_effect(self,version_id:str,*,outcome:str,errors:list[str],mapping_proposal:dict[str,object],local_validation:dict[str,object],client_validation:dict[str,object],normalized_disruption:dict[str,object]|None,catalog_version:str,schema_hash:str,context_version:str)->None:
        value=self._changed(self.get_version(version_id),mapping_outcome=outcome,mapping_errors=errors,mapping_proposal=mapping_proposal,local_validation=local_validation,client_validation=client_validation,normalized_disruption=normalized_disruption,catalog_version=catalog_version,schema_hash=schema_hash);self._save_version(value)
    def set_processing_state(self,version_id:str,state:str)->None:self._save_version(self._changed(self.get_version(version_id),processing_state=state))
    def finalize(self,version_id:str,grounding_confidence:float,mapping_confidence:float|None)->CanonicalSignal:
        value=self.get_version(version_id);state="READY_FOR_REVIEW" if value.mapping_outcome=="MAPPED" else "NEEDS_RESOLUTION" if value.mapping_outcome in {"NO_ENTITIES","UNRESOLVED_ENTITIES"} else "MAPPING_FAILED"
        value=self._changed(value,grounding_confidence=grounding_confidence,mapping_confidence=mapping_confidence,processing_state=state);self._save_version(value);return value
    def list(self,*,review_status:str|None=None,limit:int=50,continuation_token:str|None=None)->Page[CanonicalSignal]:
        identity=f"signal:{review_status or '*'}";expression=Attr("review_status").eq(review_status) if review_status else None
        rows,token=self._query_page(index="GSI1",partition="SIGNAL",limit=limit,token=continuation_token,identity=identity,ascending=False,filter_expression=expression)
        return Page(tuple(self.get_version(x["current_version_id"]) for x in rows),token)
    def review(self,signal_id:str,decision:str,*,expected_version:int|None=None)->CanonicalSignal:
        meta=self._get(f"SIGNAL#{signal_id}")
        if not meta:raise NotFoundError("Signal not found")
        current=self.get_version(meta["current_version_id"])
        if decision=="ACCEPTED":
            if any(x.status!="RESOLVED" for x in current.entities):raise ValueError("All entities must be resolved")
            if current.normalized_disruption is None:raise ValueError("Client-normalized disruption is required")
        expected=meta["version"] if expected_version is None else expected_version
        result=self._changed(current,aggregate_version=expected+1,review_status=decision,lifecycle_status="ACTIVE" if decision=="ACCEPTED" else "REJECTED")
        row=self._version_row(result.id);row.update(payload=model_payload(result),processing_state=result.processing_state.value)
        if decision=="ACCEPTED":
            row.update(GSI1PK=f"RISK#{result.context_version}",GSI1SK=result.id)
        history=[]
        for evidence_id in result.evidence_ids:
            key={"PK":f"EVIDENCE_SIGNAL#{evidence_id}","SK":f"SIGNAL#{signal_id}"};entry=self.table.get_item(Key=key,ConsistentRead=True).get("Item")
            if entry:
                attempt=parse_model(EvidenceProcessingAttempt,entry["payload"])
                entry["payload"]=model_payload(attempt.model_copy(update={"review_status":decision}))
                history.append({"Put":{"TableName":self.table.name,"Item":wire_item(entry)}})
        try:transact_write(self.table.meta.client,[
            {"Update":{"TableName":self.table.name,"Key":wire_item({"PK":meta["PK"],"SK":"META"}),"ConditionExpression":"#v = :expected","UpdateExpression":"SET #v = :next, review_status = :review","ExpressionAttributeNames":{"#v":"version"},"ExpressionAttributeValues":wire_item({":expected":expected,":next":expected+1,":review":decision})}},
            {"Put":{"TableName":self.table.name,"Item":wire_item(row)}},
            *history,
        ])
        except ConflictError as error:raise ConflictError("signal version conflict") from error
        return result
    def relate(self,source_version_id:str,target_version_id:str,*,relationship:str,confidence:float,rationale:str)->dict[str,object]:
        self._version_row(source_version_id);self._version_row(target_version_id);identifier=f"relationship-{uuid4().hex}";payload={"id":identifier,"source_signal_version_id":source_version_id,"target_signal_version_id":target_version_id,"relationship":relationship,"confidence":confidence,"rationale":rationale}
        try:
            self.table.put_item(Item={"PK":"RELATIONSHIPS","SK":identifier,"payload":encode_value(payload)})
            for version in {source_version_id,target_version_id}:self.table.put_item(Item={"PK":f"VERSION_REL#{version}","SK":identifier,"payload":encode_value(payload)})
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
        return {"id":identifier,"relationship":relationship,"confidence":confidence,"rationale":rationale}
