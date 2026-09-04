"""DynamoDB immutable experiment packages and retained result copies."""
from __future__ import annotations
from datetime import datetime
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError,ClientError
from app.domain.repository import ExperimentPreparation,ExperimentSignal,SignalRelationship,SimulationResultSnapshot
from app.integrations.contracts import ExperimentPackage
from app.repositories.dynamodb.codec import decode_value,encode_value
from app.repositories.dynamodb.common import DynamoRepository,model_payload,parse_model
from app.repositories.dynamodb.operations import raise_persistence_error,transact_write,wire_item
from app.repositories.dynamodb.signal import DynamoSignalRepository
from app.repositories.errors import ConflictError,NotFoundError

class DynamoExperimentRepository(DynamoRepository):
    def prepare(self,version_ids:list[str])->ExperimentPreparation:
        signals=[];relationships={}
        repo=DynamoSignalRepository(self.table)
        for identifier in version_ids:
            value=repo.get_version(identifier);signals.append(ExperimentSignal(identifier,value.signal_id,value.review_status,value.context_version,value.occurrence_probability,value.normalized_disruption))
            try:rows=self.table.query(KeyConditionExpression=Key("PK").eq(f"VERSION_REL#{identifier}"))["Items"]
            except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
            for row in rows:
                item=decode_value(row["payload"]);relationships[item["id"]]=SignalRelationship(item["source_signal_version_id"],item["target_signal_version_id"],item["relationship"])
        return ExperimentPreparation(tuple(signals),tuple(relationships.values()))
    def create_if_absent(self,package:ExperimentPackage)->ExperimentPackage:
        partition=f"EXPERIMENT_KEY#{package.idempotency_key}"
        try:
            lock=self._get(partition)
            if lock:
                existing=self.get(lock["experiment_id"])
                if existing:return existing
            item={"PK":f"EXPERIMENT#{package.id}","SK":"META","GSI1PK":"EXPERIMENT","GSI1SK":f"{encode_value(package.created_at)}#{package.id}","GSI2PK":partition,"GSI2SK":"META","payload":model_payload(package),"version":0,"status":package.status}
            transact_write(self.table.meta.client,[
                {"Put":{"TableName":self.table.name,"Item":wire_item({"PK":partition,"SK":"META","experiment_id":package.id}),"ConditionExpression":"attribute_not_exists(PK)"}},
                {"Put":{"TableName":self.table.name,"Item":wire_item(item),"ConditionExpression":"attribute_not_exists(PK)"}},
            ])
        except ConflictError:
            lock=self._get(partition)
            if lock:
                existing=self.get(lock["experiment_id"])
                if existing:return existing
            raise
        return package
    def get(self,experiment_id:str)->ExperimentPackage|None:
        row=self._get(f"EXPERIMENT#{experiment_id}");return parse_model(ExperimentPackage,row["payload"]) if row else None
    def mark_submitted(self,experiment_id:str,run_id:str,status:str)->ExperimentPackage:
        value=self.get(experiment_id)
        if value is None:raise NotFoundError("Experiment not found")
        if value.client_run_id is not None and value.client_run_id!=run_id:raise ConflictError("experiment package is immutable after submission")
        result=value.model_copy(update={"client_run_id":run_id,"status":status})
        try:self.table.update_item(Key={"PK":f"EXPERIMENT#{experiment_id}","SK":"META"},UpdateExpression="SET payload = :payload, #status = :status",ExpressionAttributeNames={"#status":"status"},ExpressionAttributeValues={":payload":model_payload(result),":status":status})
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
        return result
    def save_result(self,experiment_id:str,result:SimulationResultSnapshot)->None:
        package=self.get(experiment_id)
        if package is None:raise NotFoundError("Experiment not found")
        completed=package.model_copy(update={"status":"COMPLETED"});item={"PK":f"EXPERIMENT#{experiment_id}","SK":f"RESULT#{result.run_id}","GSI2PK":f"RESULT#{result.run_id}","GSI2SK":"META","payload":encode_value({"run_id":result.run_id,"context_version":result.context_version,"state_version":result.state_version,"result":result.result,"completed_at":result.completed_at})}
        transact_write(self.table.meta.client,[
            {"Put":{"TableName":self.table.name,"Item":wire_item(item)}},
            {"Update":{"TableName":self.table.name,"Key":wire_item({"PK":f"EXPERIMENT#{experiment_id}","SK":"META"}),"ConditionExpression":"attribute_exists(PK)","UpdateExpression":"SET payload = :payload, #status = :status","ExpressionAttributeNames":{"#status":"status"},"ExpressionAttributeValues":wire_item({":payload":model_payload(completed),":status":"COMPLETED"})}},
        ])
    def get_result(self,run_id:str)->SimulationResultSnapshot|None:
        try:rows=self.table.query(IndexName="GSI2",KeyConditionExpression=Key("GSI2PK").eq(f"RESULT#{run_id}"),Limit=1).get("Items",[])
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
        if not rows:return None
        value=decode_value(rows[0]["payload"])
        if isinstance(value.get("completed_at"),str):value["completed_at"]=datetime.fromisoformat(value["completed_at"].replace("Z","+00:00"))
        return SimulationResultSnapshot(**value)
