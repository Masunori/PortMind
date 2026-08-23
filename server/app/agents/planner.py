"""Generate contingency proposals and validate every action deterministically."""

import re

from pydantic import BaseModel, Field

from app.ai import AIProvider
from app.domain.exposure import ExposureAnalysis
from app.domain.plan import Plan, PlanAction, PlanActionType
from app.domain.shipment import Shipment
from app.services.network_service import get_network, get_shipments
from app.services.planning_tools import (
    get_affected_shipments,
    get_available_routes,
    get_inventory,
    get_route_capacity,
    get_transport_modes,
)


class PlanningContext(BaseModel):
    """Provide grounded exposure context to contingency planning."""

    exposure: ExposureAnalysis


class PlanActionProposal(BaseModel):
    """Represent an AI-proposed action before domain validation."""

    type: PlanActionType
    shipment_id: str | None = None
    new_route: list[str] | None = None
    alternative_inventory_node_id: str | None = None
    transit_time_multiplier: float = Field(default=1, gt=0)
    cost_multiplier: float = Field(default=1, ge=0)


class PlanProposal(BaseModel):
    """Represent one named provider proposal with explanatory rationale."""

    name: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    actions: list[PlanActionProposal] = Field(min_length=1)


class PlanProposalBatch(BaseModel):
    """Wrap plan proposals for structured provider generation."""

    proposals: list[PlanProposal] = Field(min_length=1, max_length=20)


def _slug(value: str) -> str:
    """Create a stable identifier component from a proposal name."""

    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _validate_action(
    proposal: PlanActionProposal,
    shipments_by_id: dict[str, Shipment],
) -> PlanAction:
    """Validate one proposal against shipments, routes, inventory, and capacity."""

    action = PlanAction.model_validate(proposal.model_dump())
    if action.type is PlanActionType.WAIT:
        return action
    shipment = shipments_by_id.get(action.shipment_id or "")
    if shipment is None:
        raise ValueError(f"Unknown or unaffected shipment {action.shipment_id}")
    if action.new_route is not None:
        expected_origin = (
            action.alternative_inventory_node_id
            if action.type is PlanActionType.USE_ALTERNATIVE_INVENTORY
            else shipment.origin_id
        )
        if action.new_route[0] != expected_origin:
            raise ValueError(f"Route for {shipment.id} starts at the wrong node")
        if action.new_route[-1] != shipment.destination_id:
            raise ValueError(f"Route for {shipment.id} ends at the wrong node")
        if action.new_route not in get_available_routes(
            action.new_route[0],
            action.new_route[-1],
        ):
            raise ValueError(f"Proposed route for {shipment.id} does not exist")
        if get_route_capacity(action.new_route) < shipment.quantity:
            raise ValueError(f"Proposed route lacks capacity for {shipment.id}")
    if action.type is PlanActionType.USE_ALTERNATIVE_INVENTORY:
        inventory_node = action.alternative_inventory_node_id or ""
        if get_inventory(inventory_node) < shipment.quantity:
            raise ValueError(f"Alternative inventory is insufficient for {shipment.id}")
    return action


def validate_and_convert_plans(
    context: PlanningContext,
    batch: PlanProposalBatch,
) -> list[Plan]:
    """Convert provider proposals only after deterministic capability checks."""

    affected = get_affected_shipments(context.exposure)
    shipments_by_id = {shipment.id: shipment for shipment in affected}
    plans: list[Plan] = []
    names: set[str] = set()
    for index, proposal in enumerate(batch.proposals, 1):
        name_slug = _slug(proposal.name)
        if not name_slug or name_slug in names:
            raise ValueError(f"Invalid or duplicate plan name: {proposal.name}")
        names.add(name_slug)
        actions = [
            _validate_action(action, shipments_by_id)
            for action in proposal.actions
        ]
        targeted = [
            action.shipment_id
            for action in actions
            if action.type is not PlanActionType.WAIT
        ]
        if len(targeted) != len(set(targeted)):
            raise ValueError(f"Plan {proposal.name} targets a shipment more than once")
        plans.append(
            Plan(
                id=f"generated-plan-{index}-{name_slug}",
                name=proposal.name,
                actions=actions,
            )
        )
    return plans


class ContingencyPlanner:
    """Generate proposals abstractly and enforce backend capabilities."""

    def __init__(self, provider: AIProvider) -> None:
        """Initialize the planner with an abstract provider."""

        self._provider = provider

    async def generate(self, context: PlanningContext) -> list[Plan]:
        """Generate and validate contingency plans for grounded exposure."""

        affected = get_affected_shipments(context.exposure)
        network = get_network()
        prompt = (
            f"Propose plans for shipments: {', '.join(item.id for item in affected)}; "
            f"transport modes: {', '.join(get_transport_modes(network))}"
        )
        batch = await self._provider.structured_generate(prompt, PlanProposalBatch)
        return validate_and_convert_plans(context, batch)
