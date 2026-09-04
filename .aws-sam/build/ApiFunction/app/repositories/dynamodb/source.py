"""DynamoDB source repository."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
import re
from uuid import uuid4
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError,ClientError
from app.domain.source import DataSource,DataSourceCreate,DataSourceUpdate,SourceRunStatus,SourceType
from app.repositories.contracts import Page
from app.repositories.dynamodb.codec import decode_token,encode_token,encode_value
from app.repositories.dynamodb.common import DynamoRepository,model_payload,parse_model,validate_limit
from app.repositories.dynamodb.operations import conditional_put,raise_persistence_error
from app.repositories.errors import ConflictError,NotFoundError

def _item(source:DataSource,version:int)->dict:
    item={"PK":f"SOURCE#{source.id}","SK":"META","entity":"SOURCE","version":version,
        "GSI1PK":"SOURCE","GSI1SK":f"{source.name.casefold()}#{source.id}","payload":model_payload(source)}
    if source.type is SourceType.WEBSITE and source.enabled and source.schedule_enabled and source.next_run_at:
        item.update(GSI2PK="DUE",GSI2SK=f"{encode_value(source.next_run_at)}#{source.id}")
    return item

class DynamoSourceRepository(DynamoRepository):
    def create(self,values:DataSourceCreate)->DataSource:
        now=datetime.now(timezone.utc);slug=re.sub(r"[^a-z0-9]+","-",values.name.casefold()).strip("-") or "source"
        next_run=now+timedelta(minutes=values.scrape_interval_minutes) if values.type is SourceType.WEBSITE and values.enabled and values.schedule_enabled else None
        result=DataSource(id=f"{slug}-{uuid4().hex[:8]}",**values.model_dump(),last_run_at=None,next_run_at=next_run,last_status=SourceRunStatus.NEVER,last_error=None,created_at=now,updated_at=now)
        conditional_put(self.table,_item(result,0),expected_version=None);return result
    def list(self,*,limit:int=100,continuation_token:str|None=None)->Page[DataSource]:
        return self._model_page(DataSource,index="GSI1",partition="SOURCE",limit=limit,token=continuation_token,identity="source:list")
    def get(self,source_id:str)->DataSource|None:
        row=self._get(f"SOURCE#{source_id}");return parse_model(DataSource,row["payload"]) if row else None
    def update(self,source_id:str,values:DataSourceUpdate)->DataSource|None:
        row=self._get(f"SOURCE#{source_id}")
        if not row:return None
        current=parse_model(DataSource,row["payload"]);candidate=DataSourceCreate.model_validate({**current.model_dump(),**values.model_dump(exclude_unset=True)})
        now=datetime.now(timezone.utc);next_run=now+timedelta(minutes=candidate.scrape_interval_minutes) if candidate.type is SourceType.WEBSITE and candidate.enabled and candidate.schedule_enabled else None
        result=DataSource(id=current.id,**candidate.model_dump(),last_run_at=current.last_run_at,next_run_at=next_run,last_status=current.last_status,last_error=current.last_error,created_at=current.created_at,updated_at=now)
        conditional_put(self.table,_item(result,row["version"]+1),expected_version=row["version"]);return result
    def delete(self,source_id:str)->bool:
        row=self._get(f"SOURCE#{source_id}")
        if not row:return False
        try:
            refs=self.table.query(KeyConditionExpression=Key("PK").eq(f"SOURCE_REF#{source_id}"),Limit=1,Select="COUNT",ConsistentRead=True)
            if refs.get("Count"):raise ConflictError("Sources with retained evidence cannot be deleted")
            self.table.delete_item(Key={"PK":row["PK"],"SK":"META"},ConditionExpression="#v = :v",ExpressionAttributeNames={"#v":"version"},ExpressionAttributeValues={":v":row["version"]})
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
        return True
    def due(self,now:datetime|None=None)->list[DataSource]:
        effective=encode_value(now or datetime.now(timezone.utc))
        try:rows=self.table.query(IndexName="GSI2",KeyConditionExpression=Key("GSI2PK").eq("DUE")&Key("GSI2SK").lte(f"{effective}#\uffff"))["Items"]
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
        return [parse_model(DataSource,x["payload"]) for x in rows]
    def record_run(self,source_id:str,error:str|None=None)->DataSource:
        row=self._get(f"SOURCE#{source_id}")
        if not row:raise NotFoundError("Source not found")
        old=parse_model(DataSource,row["payload"]);now=datetime.now(timezone.utc)
        result=old.model_copy(update={"last_run_at":now,"last_status":SourceRunStatus.FAILED if error else SourceRunStatus.HEALTHY,"last_error":error,"updated_at":now,"next_run_at":now+timedelta(minutes=old.scrape_interval_minutes) if old.enabled and old.schedule_enabled and old.scrape_interval_minutes else None})
        conditional_put(self.table,_item(result,row["version"]+1),expected_version=row["version"]);return result
    def acquire_lease(self,source_id:str,owner:str,*,now:datetime,expires_at:datetime)->bool:
        try:
            self.table.put_item(Item={"PK":f"SOURCE#{source_id}","SK":"LEASE","lease_owner":owner,"lease_until":encode_value(expires_at)},ConditionExpression="attribute_not_exists(PK) OR lease_until <= :now",ExpressionAttributeValues={":now":encode_value(now)})
            return True
        except ClientError as error:
            if error.response.get("Error",{}).get("Code")=="ConditionalCheckFailedException":return False
            raise_persistence_error(error)
        except BotoCoreError as error:raise_persistence_error(error)
    def release_lease(self,source_id:str,owner:str)->None:
        try:self.table.delete_item(Key={"PK":f"SOURCE#{source_id}","SK":"LEASE"},ConditionExpression="lease_owner = :owner",ExpressionAttributeValues={":owner":owner})
        except ClientError as error:
            if error.response.get("Error",{}).get("Code")!="ConditionalCheckFailedException":raise_persistence_error(error)
        except BotoCoreError as error:raise_persistence_error(error)
