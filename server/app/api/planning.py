"""Refreshable planning-cycle API with an explicit human decision boundary."""

from datetime import datetime
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.domain.plan import PlanningCycle, PlanningLifecycle
from app.integrations import (
    get_client_gateway, get_hypothesis_provider, get_planner_provider, get_risk_provider,
)
from app.integrations.contracts import (
    GenerationEntity, HypothesisGenerationRequest, HypothesisGenerationResponse, HypothesisSignalProposal,
    EntitySearchRequest,
)
from app.integrations.errors import ClientGatewayError
from app.integrations.bedrock import BedrockAPIError
from app.integrations.gemini import GeminiAPIError
from app.integrations.gateway import ClientGateway
from app.integrations.providers import HypothesisProvider
from app.integrations.schema_validation import admit_schema, validate_payload
from app.services.planning_service import PlanningService, get_cycle, list_cycles, save_cycle
from app.repositories.errors import ConflictError

router = APIRouter(prefix="/api/planning/cycles", tags=["planning"])


class CycleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planning_starts_at: datetime | None = None
    planning_ends_at: datetime | None = None
    generation_limit: int = Field(default=5, ge=1, le=20)
    planner_mode: Literal["single", "panel"] = "single"
    panel_agent_count: int = Field(default=3, ge=1, le=5)
    confirmed_hypotheses: list[HypothesisSignalProposal] = Field(default_factory=list, max_length=10)
    objectives: list[str] = Field(default_factory=list, max_length=50)
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    entity_scope: list[GenerationEntity] = Field(default_factory=list, max_length=1000)


class HypothesisGenerationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=5000)
    entity_scope: list[GenerationEntity] = Field(default_factory=list, max_length=1000)
    generation_limit: int = Field(default=3, ge=1, le=10)


class GenerationEntitySearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=300)
    entity_types: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=10, ge=1, le=50)


class PlanGeneration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    known_entity_ids: list[str] = Field(default_factory=list, max_length=1000)
    objectives: list[str] = Field(default_factory=list, max_length=50)
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    proposal_limit: int = Field(default=5, ge=0, le=20)


class ScenarioSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disruption_ids: list[str] = Field(min_length=1, max_length=20)


def service(planner_mode: str = "single", panel_agent_count: int = 3) -> PlanningService:
    return PlanningService(get_risk_provider(), get_planner_provider(planner_mode, panel_agent_count))


def required(cycle_id: str) -> PlanningCycle:
    cycle = get_cycle(cycle_id)
    if cycle is None: raise HTTPException(404, "Planning cycle not found")
    return cycle


def provider_failure(error: BedrockAPIError | GeminiAPIError) -> HTTPException:
    return HTTPException(status_code=429 if error.status_code == 429 else 502,
        detail={"code": "MODEL_PROVIDER_ERROR", "message": str(error)})


@router.get("", response_model=list[PlanningCycle])
def cycles() -> list[PlanningCycle]: return list_cycles()


@router.get("/{cycle_id}", response_model=PlanningCycle)
def cycle(cycle_id: str) -> PlanningCycle: return required(cycle_id)


@router.post("/hypotheses/generate", response_model=HypothesisGenerationResponse)
async def generate_hypotheses(body: HypothesisGenerationBody,
        gateway: ClientGateway = Depends(get_client_gateway),
        provider: HypothesisProvider = Depends(get_hypothesis_provider)) -> HypothesisGenerationResponse:
    if not body.entity_scope:
        raise HTTPException(422, "Search for and add at least one entity before generating hypotheses")
    try:
        context = await gateway.get_context()
        catalog = await gateway.get_disruption_contracts()
        if catalog.context_version != context.context_version:
            raise ValueError("Disruption catalog context is stale")
        response = await provider.propose_hypotheses(HypothesisGenerationRequest(
            prompt=body.prompt, context_summary=context.compact_context,
            context_version=context.context_version, disruption_contracts=catalog.contracts,
            entity_scope=body.entity_scope, generation_limit=body.generation_limit))
        contracts = {item.type: item for item in catalog.contracts}
        scope = {item.entity_id: item for item in body.entity_scope}
        for item in response.hypotheses:
            contract = contracts.get(item.signal_type)
            if contract is None: raise ValueError(f"Unknown disruption type: {item.signal_type}")
            admit_schema(contract.payload_schema)
            errors = validate_payload(item.payload, contract.payload_schema)
            if errors: raise ValueError(f"Invalid hypothesis payload: {errors}")
            targets = item.payload.get("target_ids", [])
            if not isinstance(targets, list) or any(
                not isinstance(target, str) or target not in scope for target in targets
            ):
                raise ValueError("Hypothesis references an unknown entity ID")
            valid_types = {item.casefold() for item in contract.target_types}
            if any(scope[target].entity_type.casefold() not in valid_types for target in targets):
                raise ValueError("Hypothesis references an incompatible entity type")
        return response
    except (BedrockAPIError, GeminiAPIError) as error:
        raise provider_failure(error) from error
    except ClientGatewayError as error:
        raise HTTPException(502, {"code": error.code, "message": str(error)}) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/entities/search", response_model=list[GenerationEntity])
async def search_generation_entities(body: GenerationEntitySearchBody,
        gateway: ClientGateway = Depends(get_client_gateway)) -> list[GenerationEntity]:
    """Search the authoritative client registry without expanding scope implicitly."""
    try:
        context = await gateway.get_context()
        response = await gateway.search_entities(EntitySearchRequest(query=body.query,
            entity_types=body.entity_types, context_version=context.context_version,
            limit=body.limit))
        if response.context_version != context.context_version:
            raise ValueError("Entity search returned a stale context")
        return [GenerationEntity(entity_id=item.entity_id, entity_type=item.entity_type,
            display_name=item.display_name) for item in response.candidates]
    except ClientGatewayError as error:
        raise HTTPException(502, {"code": error.code, "message": str(error)}) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("", response_model=PlanningCycle, status_code=201)
async def create_cycle(body: CycleCreate, gateway: ClientGateway = Depends(get_client_gateway)) -> PlanningCycle:
    planner = service()
    try:
        return save_cycle(await planner.create_draft(gateway=gateway,
            planning_starts_at=body.planning_starts_at, planning_ends_at=body.planning_ends_at,
            generation_limit=body.generation_limit,
            confirmed_hypotheses=body.confirmed_hypotheses,
            entity_scope=body.entity_scope,
            planner_mode=body.planner_mode, panel_agent_count=body.panel_agent_count,
            planning_objectives=body.objectives,
            hard_constraints=body.hard_constraints))
    except (BedrockAPIError, GeminiAPIError) as error:
        raise provider_failure(error) from error
    except ClientGatewayError as error:
        raise HTTPException(502, {"code": error.code, "message": str(error)}) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/{cycle_id}/scenario", response_model=PlanningCycle)
def select_scenario(cycle_id: str, body: ScenarioSelection) -> PlanningCycle:
    try:
        current = required(cycle_id)
        return save_cycle(service(current.planner_mode, current.panel_agent_count).compose_scenario(current, body.disruption_ids), expected_version=current.version)
    except ConflictError as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


async def _advance_to_approval(cycle: PlanningCycle, *, planner: PlanningService,
                               gateway: ClientGateway) -> PlanningCycle:
    """Advance every non-human step once, stopping only for polling or approval."""
    if cycle.baseline_metrics is None and cycle.baseline_run_id is not None:
        cycle = await planner.refresh_baseline(cycle, gateway=gateway)
    if cycle.status == PlanningLifecycle.FAILED or cycle.baseline_metrics is None:
        return cycle
    if not cycle.plans:
        try:
            cycle = await planner.propose_plans(cycle, gateway=gateway,
                objectives=cycle.planning_objectives or ["minimize late shipments",
                    "minimize average delay", "minimize total cost"],
                hard_constraints=cycle.hard_constraints)
        except ClientGatewayError as error:
            # Baseline results are independently authoritative. Preserve them even when
            # the client's optional next-step capability is temporarily unavailable;
            # an explicit proposal request will still surface the integration error.
            return cycle.model_copy(update={"error_code": error.code,
                "error_message": f"Plan generation unavailable: {error}"})
        if not cycle.plans:
            return cycle.model_copy(update={"status": PlanningLifecycle.EVALUATED})
    for plan in list(cycle.plans):
        current = next(item for item in cycle.plans if item.id == plan.id)
        if current.status == PlanningLifecycle.VALIDATED and current.intervention_run_id is None:
            cycle = await planner.submit_plan(cycle, current.id, gateway=gateway)
        elif current.status == PlanningLifecycle.RUNNING:
            cycle = await planner.refresh_plan(cycle, current.id, gateway=gateway)
    terminal = {PlanningLifecycle.EVALUATED, PlanningLifecycle.FAILED,
                PlanningLifecycle.RECOMMENDED}
    if (cycle.plans and all(item.status in terminal for item in cycle.plans)
            and any(item.status == PlanningLifecycle.EVALUATED for item in cycle.plans)
            and not any(item.status == PlanningLifecycle.RECOMMENDED for item in cycle.plans)):
        cycle = planner.rank(cycle)
    return cycle


# Kept as an internal compatibility alias for callers from the previous iteration.
_propose_after_result = _advance_to_approval


@router.post("/{cycle_id}/baseline/submit", response_model=PlanningCycle)
async def submit_baseline(cycle_id: str,
                          gateway: ClientGateway = Depends(get_client_gateway)) -> PlanningCycle:
    current = required(cycle_id)
    planner = service(current.planner_mode, current.panel_agent_count)
    try:
        cycle = await planner.submit_baseline(current, gateway=gateway)
        return save_cycle(await _advance_to_approval(cycle, planner=planner, gateway=gateway), expected_version=current.version)
    except (BedrockAPIError, GeminiAPIError) as error:
        raise provider_failure(error) from error
    except ClientGatewayError as error:
        raise HTTPException(502, {"code": error.code, "message": str(error)}) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/{cycle_id}/baseline/refresh", response_model=PlanningCycle)
async def refresh_baseline(cycle_id: str, gateway: ClientGateway = Depends(get_client_gateway)) -> PlanningCycle:
    current = required(cycle_id)
    planner = service(current.planner_mode, current.panel_agent_count)
    try:
        return save_cycle(await _advance_to_approval(current, planner=planner, gateway=gateway), expected_version=current.version)
    except (BedrockAPIError, GeminiAPIError) as error:
        raise provider_failure(error) from error
    except ClientGatewayError as error:
        raise HTTPException(502, {"code": error.code, "message": str(error)}) from error


@router.post("/{cycle_id}/proposals", response_model=PlanningCycle)
async def proposals(cycle_id: str, body: PlanGeneration,
                    gateway: ClientGateway = Depends(get_client_gateway)) -> PlanningCycle:
    current = required(cycle_id)
    try:
        return save_cycle(await service(current.planner_mode, current.panel_agent_count).propose_plans(current, gateway=gateway,
            known_entity_ids=body.known_entity_ids or None, objectives=body.objectives,
            hard_constraints=body.hard_constraints, proposal_limit=body.proposal_limit), expected_version=current.version)
    except (BedrockAPIError, GeminiAPIError) as error:
        raise provider_failure(error) from error
    except ClientGatewayError as error:
        raise HTTPException(502, {"code": error.code, "message": str(error)}) from error


@router.post("/{cycle_id}/plans/{plan_id}/submit", response_model=PlanningCycle)
async def submit_plan(cycle_id: str, plan_id: str,
                      gateway: ClientGateway = Depends(get_client_gateway)) -> PlanningCycle:
    current = required(cycle_id)
    try:
        return save_cycle(await service(current.planner_mode, current.panel_agent_count).submit_plan(current, plan_id, gateway=gateway), expected_version=current.version)
    except ClientGatewayError as error:
        raise HTTPException(502, {"code": error.code, "message": str(error)}) from error


@router.post("/{cycle_id}/plans/{plan_id}/refresh", response_model=PlanningCycle)
async def refresh_plan(cycle_id: str, plan_id: str,
                       gateway: ClientGateway = Depends(get_client_gateway)) -> PlanningCycle:
    current = required(cycle_id)
    try:
        planner = service(current.planner_mode, current.panel_agent_count)
        cycle = await planner.refresh_plan(current, plan_id, gateway=gateway)
        return save_cycle(await _advance_to_approval(cycle, planner=planner, gateway=gateway), expected_version=current.version)
    except (BedrockAPIError, GeminiAPIError) as error:
        raise provider_failure(error) from error
    except ClientGatewayError as error:
        raise HTTPException(502, {"code": error.code, "message": str(error)}) from error


@router.post("/{cycle_id}/advance", response_model=PlanningCycle)
async def advance(cycle_id: str,
                  gateway: ClientGateway = Depends(get_client_gateway)) -> PlanningCycle:
    """Poll and execute all machine-owned workflow steps up to human approval."""
    current = required(cycle_id)
    planner = service(current.planner_mode, current.panel_agent_count)
    try:
        return save_cycle(await _advance_to_approval(current, planner=planner, gateway=gateway), expected_version=current.version)
    except (BedrockAPIError, GeminiAPIError) as error:
        raise provider_failure(error) from error
    except ClientGatewayError as error:
        raise HTTPException(502, {"code": error.code, "message": str(error)}) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/{cycle_id}/rank", response_model=PlanningCycle)
def rank(cycle_id: str) -> PlanningCycle:
    current = required(cycle_id)
    return save_cycle(service(current.planner_mode, current.panel_agent_count).rank(current), expected_version=current.version)


def decide(cycle_id: str, plan_id: str, decision: PlanningLifecycle) -> PlanningCycle:
    current = required(cycle_id)
    return save_cycle(service(current.planner_mode, current.panel_agent_count).decide(current, plan_id, decision), expected_version=current.version)


@router.post("/{cycle_id}/plans/{plan_id}/approve", response_model=PlanningCycle)
def approve(cycle_id: str, plan_id: str) -> PlanningCycle:
    return decide(cycle_id, plan_id, PlanningLifecycle.APPROVED)


@router.post("/{cycle_id}/plans/{plan_id}/reject", response_model=PlanningCycle)
def reject(cycle_id: str, plan_id: str) -> PlanningCycle:
    return decide(cycle_id, plan_id, PlanningLifecycle.REJECTED)
