"""DynamoDB prompt, scenario, and plan definition repositories."""
from __future__ import annotations
from datetime import datetime,timezone
from typing import get_args
from botocore.exceptions import BotoCoreError,ClientError
from app.domain.plan import Plan,PlanStatus
from app.domain.prompt import AgentName,AgentPrompt
from app.domain.scenario import Scenario
from app.repositories.contracts import Page
from app.repositories.dynamodb.codec import decode_token,encode_token
from app.repositories.dynamodb.common import DynamoRepository,model_payload,parse_model,validate_limit
from app.repositories.dynamodb.operations import raise_persistence_error

class _DefinitionRepository(DynamoRepository):
    model_type=None;kind=""
    def save(self,value):
        item={"PK":f"{self.kind}#{value.id}","SK":"META","GSI1PK":self.kind,"GSI1SK":value.id,"payload":model_payload(value)}
        try:self.table.put_item(Item=item)
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
        return value
    def get(self,item_id):
        row=self._get(f"{self.kind}#{item_id}");return parse_model(self.model_type,row["payload"]) if row else None
    def list(self,*,limit=100,continuation_token=None):
        return self._model_page(self.model_type,index="GSI1",partition=self.kind,limit=limit,token=continuation_token,identity=f"{self.kind.lower()}:list")
class DynamoScenarioRepository(_DefinitionRepository):model_type=Scenario;kind="SCENARIO"
class DynamoPlanRepository(_DefinitionRepository):
    model_type=Plan;kind="PLAN"
    def set_status(self,plan_id:str,status:PlanStatus)->Plan|None:
        plan=self.get(plan_id)
        if plan is None:return None
        if status in {PlanStatus.APPROVED,PlanStatus.REJECTED} and plan.status is not PlanStatus.RECOMMENDED:raise ValueError("Only a recommended plan can receive a human decision")
        return self.save(plan.model_copy(update={"status":status}))

class DynamoPromptRepository(DynamoRepository):
    agents=tuple(get_args(AgentName))
    def get(self,agent:AgentName)->AgentPrompt|None:
        row=self._get(f"PROMPT#{agent}");return parse_model(AgentPrompt,row["payload"]) if row else None
    def save(self,agent:AgentName,prompt:str)->AgentPrompt:
        if agent not in self.agents:raise ValueError("Unsupported agent")
        result=AgentPrompt(agent=agent,prompt=prompt,is_custom=True,updated_at=datetime.now(timezone.utc))
        try:self.table.put_item(Item={"PK":f"PROMPT#{agent}","SK":"META","payload":model_payload(result)})
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
        return result
    def reset(self,agent:AgentName)->bool:
        try:return bool(self.table.delete_item(Key={"PK":f"PROMPT#{agent}","SK":"META"},ReturnValues="ALL_OLD").get("Attributes"))
        except (BotoCoreError,ClientError) as error:raise_persistence_error(error)
    def list(self,*,limit:int=100,continuation_token:str|None=None)->Page[AgentPrompt]:
        validate_limit(limit);state=decode_token(continuation_token,query_identity="prompt:list") or {"offset":0};offset=int(state["offset"])
        selected=self.agents[offset:offset+limit];items=[item for item in (self.get(agent) for agent in selected) if item]
        next_offset=offset+limit;token=encode_token({"offset":next_offset},query_identity="prompt:list") if next_offset<len(self.agents) else None
        return Page(tuple(items),token)
