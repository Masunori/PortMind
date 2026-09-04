"""DynamoDB evidence aggregate, content chunks, and reverse protections."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json,re
from uuid import uuid4
from boto3.dynamodb.conditions import Attr,Key
from botocore.exceptions import BotoCoreError,ClientError
from app.integrations.contracts import (DeletionImpact,DuplicateDeletionCandidate,DuplicateDeletionPreview,DuplicateDeletionResult,Evidence,EvidenceCreate,EvidenceKind,EvidenceUpdate,ProcessingStatus,RetentionClass)
from app.repositories.contracts import Page
from app.repositories.dynamodb.codec import chunk_content,decode_value,encode_value,reconstruct_content
from app.repositories.dynamodb.common import DynamoRepository,model_payload,parse_model,validate_limit
from app.repositories.dynamodb.operations import raise_persistence_error,transact_write,wire_item
from app.repositories.errors import ConflictError,NotFoundError,ValidationError

def _normalized(value:str)->str:return re.sub(r"\s+"," ",value).strip()
def _digest(v:EvidenceCreate)->str:
    raw=_normalized(v.content) if v.content is not None else json.dumps(v.structured_content,sort_keys=True,separators=(",",":")) if v.structured_content is not None else v.content_reference or ""
    return hashlib.sha256(raw.encode()).hexdigest()
def _meta(value:Evidence)->dict:
    payload=value.model_copy(update={"content":None,"content_reference":value.content_reference or ("chunks://content" if value.content is not None else None)})
    return {"PK":f"EVIDENCE#{value.id}","SK":"META","entity":"EVIDENCE","GSI1PK":"EVIDENCE","GSI1SK":f"{encode_value(value.collected_at)}#{value.id}","GSI2PK":f"HASH#{value.content_hash}","GSI2SK":f"{encode_value(value.collected_at)}#{value.id}","archived":value.archived_at is not None,"kind":value.kind.value,"duplicate":value.duplicate_of_id is not None,"payload":model_payload(payload),"version":0}

class DynamoEvidenceRepository(DynamoRepository):
    def _write(self,value:Evidence,chunks:list[bytes]|None=None)->None:
        try:
            self.table.put_item(Item=_meta(value))
            if chunks is not None:
                with self.table.batch_writer() as writer:
                    for index,chunk in enumerate(chunks):writer.put_item(Item={"PK":f"EVIDENCE#{value.id}","SK":f"CONTENT#{index:06d}","content":chunk})
            self.table.put_item(Item={"PK":f"SOURCE_REF#{value.source_id}","SK":f"EVIDENCE#{value.id}","evidence_id":value.id})
            if value.duplicate_of_id:self.table.put_item(Item={"PK":f"DUP_REF#{value.duplicate_of_id}","SK":f"EVIDENCE#{value.id}","evidence_id":value.id})
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
    def store(self,values:EvidenceCreate)->tuple[Evidence,bool]:
        chunks,dummy=chunk_content(_normalized(values.content)) if values.content is not None else ([],"")
        if self._get(f"SOURCE#{values.source_id}") is None:raise NotFoundError("Source not found")
        digest=_digest(values);now=datetime.now(timezone.utc)
        lock=self._get(f"HASH#{digest}");canonical=self.get(lock["canonical_id"]) if lock else None;identifier=f"evidence-{uuid4().hex}"
        result=Evidence(id=identifier,source_id=values.source_id,collection_run_id=values.collection_run_id,kind=values.kind,title=values.title,media_type=values.media_type,content=None if canonical else (_normalized(values.content) if values.content is not None else None),structured_content=None if canonical else values.structured_content,content_reference=None if canonical else values.content_reference,content_hash=digest,duplicate_of_id=canonical.id if canonical else None,source_url=values.source_url,published_at=values.published_at,collected_at=values.collected_at or now,processed_at=now if values.processing_status is not ProcessingStatus.PENDING else None,processing_status=values.processing_status,parser_warnings=values.parser_warnings,quality_metadata=values.quality_metadata,retention_class=values.retention_class,expires_at=values.expires_at,archived_at=None)
        table_name=self.table.name
        if canonical:
            transact_write(self.table.meta.client,[
                {"ConditionCheck":{"TableName":table_name,"Key":wire_item({"PK":f"SOURCE#{values.source_id}","SK":"META"}),"ConditionExpression":"attribute_exists(PK)"}},
                {"Put":{"TableName":table_name,"Item":wire_item(_meta(result)),"ConditionExpression":"attribute_not_exists(PK)"}},
                {"Put":{"TableName":table_name,"Item":wire_item({"PK":f"SOURCE_REF#{result.source_id}","SK":f"EVIDENCE#{result.id}","evidence_id":result.id})}},
                {"Put":{"TableName":table_name,"Item":wire_item({"PK":f"DUP_REF#{canonical.id}","SK":f"EVIDENCE#{result.id}","evidence_id":result.id})}},
            ]);return result,True
        try:
            actions=[
                {"ConditionCheck":{"TableName":table_name,"Key":wire_item({"PK":f"SOURCE#{values.source_id}","SK":"META"}),"ConditionExpression":"attribute_exists(PK)"}},
                {"Put":{"TableName":table_name,"Item":wire_item({"PK":f"HASH#{digest}","SK":"META","canonical_id":identifier}),"ConditionExpression":"attribute_not_exists(PK)"}},
                {"Put":{"TableName":table_name,"Item":wire_item(_meta(result)),"ConditionExpression":"attribute_not_exists(PK)"}},
                {"Put":{"TableName":table_name,"Item":wire_item({"PK":f"SOURCE_REF#{result.source_id}","SK":f"EVIDENCE#{result.id}","evidence_id":result.id})}},
                *({"Put":{"TableName":table_name,"Item":wire_item({"PK":f"EVIDENCE#{result.id}","SK":f"CONTENT#{index:06d}","content":chunk})}} for index,chunk in enumerate(chunks)),
            ]
            transact_write(self.table.meta.client,actions)
        except ConflictError as error:
            winner=self._get(f"HASH#{digest}")
            if not winner:raise ConflictError("concurrent evidence creation failed") from error
            canonical=self.get(winner["canonical_id"])
            if not canonical:raise ConflictError("canonical evidence is not available") from error
            result=result.model_copy(update={"content":None,"structured_content":None,"content_reference":None,"duplicate_of_id":canonical.id})
            transact_write(self.table.meta.client,[
                {"Put":{"TableName":table_name,"Item":wire_item(_meta(result)),"ConditionExpression":"attribute_not_exists(PK)"}},
                {"Put":{"TableName":table_name,"Item":wire_item({"PK":f"SOURCE_REF#{result.source_id}","SK":f"EVIDENCE#{result.id}","evidence_id":result.id})}},
                {"Put":{"TableName":table_name,"Item":wire_item({"PK":f"DUP_REF#{canonical.id}","SK":f"EVIDENCE#{result.id}","evidence_id":result.id})}},
            ]);return result,True
        return result,False
    def get(self,evidence_id:str)->Evidence|None:
        row=self._get(f"EVIDENCE#{evidence_id}")
        if not row:return None
        result=parse_model(Evidence,row["payload"])
        if result.content_reference=="chunks://content":
            try:items=self.table.query(KeyConditionExpression=Key("PK").eq(row["PK"])&Key("SK").begins_with("CONTENT#"),ConsistentRead=True)["Items"]
            except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
            result=result.model_copy(update={"content":reconstruct_content([bytes(x["content"]) for x in items]),"content_reference":None})
        return result
    def list(self,*,archived:bool|None=False,kind:EvidenceKind|None=None,include_duplicates:bool=False,limit:int=50,continuation_token:str|None=None)->Page[Evidence]:
        validate_limit(limit);identity=f"evidence:{archived}:{kind.value if kind else '*'}:{include_duplicates}"
        # DynamoDB filters can produce short pages; the continuation key remains stable.
        expression=None
        if archived is not None:expression=Attr("archived").eq(archived)
        if kind:expression=(expression&Attr("kind").eq(kind.value)) if expression else Attr("kind").eq(kind.value)
        if not include_duplicates:expression=(expression&Attr("duplicate").eq(False)) if expression else Attr("duplicate").eq(False)
        rows,token=self._query_page(index="GSI1",partition="EVIDENCE",limit=limit,token=continuation_token,identity=identity,ascending=False,filter_expression=expression)
        return Page(tuple(self.get(parse_model(Evidence,x["payload"]).id) for x in rows),token)
    def has_signal(self,evidence_id:str)->bool:return self._count(f"EVIDENCE_SIGNAL#{evidence_id}")>0
    def _count(self,pk:str)->int:
        try:return int(self.table.query(KeyConditionExpression=Key("PK").eq(pk),Select="COUNT",ConsistentRead=True).get("Count",0))
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
    def _require(self,evidence_id:str)->Evidence:
        value=self.get(evidence_id)
        if value is None:raise NotFoundError("Evidence not found")
        return value
    def set_archived(self,evidence_id:str,archived:bool)->Evidence:
        value=self._require(evidence_id).model_copy(update={"archived_at":datetime.now(timezone.utc) if archived else None});self._replace(value);return value
    def deletion_impact(self,evidence_id:str)->DeletionImpact:
        value=self._require(evidence_id);signal=self._count(f"EVIDENCE_SIGNAL#{evidence_id}");duplicates=self._count(f"DUP_REF#{evidence_id}");hold=value.retention_class is RetentionClass.LEGAL_HOLD
        protected=((['signal_versions'] if signal else [])+(['duplicate_evidence'] if duplicates else [])+(['legal_hold'] if hold else []))
        return DeletionImpact(evidence_id=evidence_id,can_remove_raw_content=not hold,can_delete_permanently=not protected,protected_by=protected,raw_content_present=any((value.content,value.structured_content,value.content_reference)))
    def duplicate_deletion_preview(self,evidence_id:str)->DuplicateDeletionPreview:
        canonical=self._require(evidence_id)
        if canonical.duplicate_of_id:raise ValidationError("Batch cleanup must target canonical evidence")
        ids=self._ref_ids(f"DUP_REF#{evidence_id}");items=[DuplicateDeletionCandidate(evidence_id=x,can_delete=(impact:=self.deletion_impact(x)).can_delete_permanently,protected_by=impact.protected_by) for x in ids]
        return DuplicateDeletionPreview(canonical_evidence_id=evidence_id,candidates=items)
    def _ref_ids(self,pk:str)->list[str]:
        try:return [x["evidence_id"] for x in self.table.query(KeyConditionExpression=Key("PK").eq(pk),ConsistentRead=True)["Items"]]
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
    def delete_unprotected_duplicates(self,evidence_id:str,*,delete_canonical:bool=False)->DuplicateDeletionResult:
        preview=self.duplicate_deletion_preview(evidence_id);deleted=[];skipped=[]
        for candidate in preview.candidates:
            if candidate.can_delete:self.delete(candidate.evidence_id);deleted.append(candidate.evidence_id)
            else:skipped.append(candidate)
        canonical_deleted=False
        if delete_canonical and self.deletion_impact(evidence_id).can_delete_permanently:self.delete(evidence_id);canonical_deleted=True
        return DuplicateDeletionResult(canonical_evidence_id=evidence_id,deleted_ids=deleted,skipped=skipped,canonical_deleted=canonical_deleted)
    def remove_raw_content(self,evidence_id:str)->Evidence:
        if not self.deletion_impact(evidence_id).can_remove_raw_content:raise ConflictError("Evidence is on legal hold")
        value=self._require(evidence_id).model_copy(update={"content":None,"structured_content":None,"content_reference":"removed://retained-audit-metadata"});self._delete_chunks(evidence_id);self._replace(value);return value
    def update(self,evidence_id:str,values:EvidenceUpdate)->Evidence:
        if self.deletion_impact(evidence_id).protected_by:raise ConflictError("Evidence linked to an audit workflow cannot be edited")
        old=self._require(evidence_id);changes=values.model_dump(exclude_unset=True);content=changes.get("content")
        if content is not None:content=_normalized(content);changes["content"]=content
        candidate=old.model_copy(update=changes)
        create=EvidenceCreate(**candidate.model_dump(exclude={"id","content_hash","duplicate_of_id","processed_at","archived_at"}));candidate=candidate.model_copy(update={"content_hash":_digest(create),"processed_at":datetime.now(timezone.utc)})
        self._delete_chunks(evidence_id);chunks,_=chunk_content(candidate.content) if candidate.content is not None else (None,None);self._write(candidate,chunks);return candidate
    def _replace(self,value:Evidence)->None:self.table.put_item(Item=_meta(value))
    def _delete_chunks(self,evidence_id:str)->None:
        try:
            rows=self.table.query(KeyConditionExpression=Key("PK").eq(f"EVIDENCE#{evidence_id}")&Key("SK").begins_with("CONTENT#"),ProjectionExpression="PK, SK")["Items"]
            with self.table.batch_writer() as writer:
                for row in rows:writer.delete_item(Key=row)
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
    def delete(self,evidence_id:str)->None:
        impact=self.deletion_impact(evidence_id)
        if not impact.can_delete_permanently:raise ConflictError("Evidence linked to an audit workflow cannot be deleted")
        value=self._require(evidence_id);self._delete_chunks(evidence_id)
        try:
            with self.table.batch_writer() as writer:
                writer.delete_item(Key={"PK":f"EVIDENCE#{evidence_id}","SK":"META"});writer.delete_item(Key={"PK":f"SOURCE_REF#{value.source_id}","SK":f"EVIDENCE#{evidence_id}"})
                if value.duplicate_of_id:writer.delete_item(Key={"PK":f"DUP_REF#{value.duplicate_of_id}","SK":f"EVIDENCE#{evidence_id}"})
                else:writer.delete_item(Key={"PK":f"HASH#{value.content_hash}","SK":"META"})
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
