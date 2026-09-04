"""DynamoDB versioned planning snapshots and indexed preparation reads."""
from __future__ import annotations
from datetime import datetime,timezone
import json
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError,ClientError
from app.domain.plan import PlanningCycle
from app.domain.repository import GroundedEntitySnapshot,RiskCandidateSnapshot,SignalRelationship
from app.repositories.contracts import Page
from app.repositories.dynamodb.codec import decode_value,encode_value
from app.repositories.dynamodb.common import DynamoRepository,model_payload,parse_model
from app.repositories.dynamodb.operations import raise_persistence_error,transact_write,wire_item
from app.repositories.dynamodb.signal import DynamoSignalRepository
from app.repositories.errors import ConflictError

class DynamoPlanningCycleRepository(DynamoRepository):
    def save(self,cycle:PlanningCycle,*,expected_version:int|None=None)->PlanningCycle:
        row=self._get(f"PLANNING#{cycle.id}");current=int(row["version"]) if row else 0
        if (row is None and expected_version not in (None,0)) or (row is not None and expected_version is not None and expected_version!=current):raise ConflictError("planning cycle version conflict")
        result=cycle.model_copy(deep=True,update={"version":current+1});raw=result.model_dump_json().encode();chunks=[raw[x:x+60*1024] for x in range(0,len(raw),60*1024)]
        if len(chunks)>90:raise ValueError("planning snapshot exceeds transaction storage limit")
        item={"PK":f"PLANNING#{cycle.id}","SK":"META","version":current+1,"GSI1PK":"PLANNING","GSI1SK":cycle.id,"chunk_count":len(chunks),"updated_at":encode_value(datetime.now(timezone.utc))}
        try:
            put={"TableName":self.table.name,"Item":wire_item(item),"ConditionExpression":"#v = :v" if row else "attribute_not_exists(PK)"}
            if row:put.update(ExpressionAttributeNames={"#v":"version"},ExpressionAttributeValues=wire_item({":v":current}))
            old=[]
            if row:
                old=self.table.query(KeyConditionExpression=Key("PK").eq(item["PK"])&Key("SK").begins_with("SECTION#"),ProjectionExpression="PK, SK",ConsistentRead=True)["Items"]
            stale=[key for key in old if int(key["SK"].rsplit("#",1)[1])>=len(chunks)]
            actions=[{"Put":put},*({"Delete":{"TableName":self.table.name,"Key":wire_item(key)}} for key in stale),*({"Put":{"TableName":self.table.name,"Item":wire_item({"PK":item["PK"],"SK":f"SECTION#SNAPSHOT#{index:06d}","content":chunk})}} for index,chunk in enumerate(chunks))]
            transact_write(self.table.meta.client,actions)
        except ClientError as error:
            if error.response.get("Error",{}).get("Code")=="ConditionalCheckFailedException":raise ConflictError("planning cycle version conflict") from error
            raise_persistence_error(error)
        except BotoCoreError as error:raise_persistence_error(error)
        return result
    def get(self,cycle_id:str)->PlanningCycle|None:
        row=self._get(f"PLANNING#{cycle_id}")
        if not row:return None
        try:chunks=self.table.query(KeyConditionExpression=Key("PK").eq(row["PK"])&Key("SK").begins_with("SECTION#SNAPSHOT#"),ConsistentRead=True)["Items"]
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
        return PlanningCycle.model_validate_json(b"".join(bytes(x["content"]) for x in chunks))
    def list(self,*,limit:int=100,continuation_token:str|None=None)->Page[PlanningCycle]:
        rows,token=self._query_page(index="GSI1",partition="PLANNING",limit=limit,token=continuation_token,identity="planning:list")
        return Page(tuple(self.get(row["PK"].removeprefix("PLANNING#")) for row in rows),token)
    def relationships(self)->list[SignalRelationship]:
        try:rows=self.table.query(KeyConditionExpression=Key("PK").eq("RELATIONSHIPS"))["Items"]
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
        return [SignalRelationship((x:=decode_value(row["payload"]))["source_signal_version_id"],x["target_signal_version_id"],x["relationship"]) for row in rows]
    def risk_candidates(self,context_version:str)->list[RiskCandidateSnapshot]:
        try:rows=self.table.query(IndexName="GSI1",KeyConditionExpression=Key("GSI1PK").eq(f"RISK#{context_version}"))["Items"]
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
        values=[parse_model(__import__('app.integrations.contracts',fromlist=['CanonicalSignal']).CanonicalSignal,row["payload"]) for row in rows]
        return [RiskCandidateSnapshot(x.id,x.classification.value,x.signal_type,x.temporal_window.model_dump(mode="python"),x.occurrence_probability,x.normalized_disruption,tuple(sorted({e.entity_id for e in x.entities if e.entity_id}))) for x in values if x.processing_state.value=="READY_FOR_REVIEW" and x.classification.value in {"OBSERVED","FORECAST"} and x.normalized_disruption is not None]
    def grounded_entities(self,version_ids:list[str],entity_ids:set[str],context_version:str)->list[GroundedEntitySnapshot]:
        if not version_ids or not entity_ids:return []
        repo=DynamoSignalRepository(self.table);result=[]
        for identifier in version_ids:
            for item in repo.get_version(identifier).entities:
                if item.entity_id in entity_ids and item.context_version==context_version and item.entity_type:result.append(GroundedEntitySnapshot(item.entity_id,item.entity_type,item.mention))
        return result
