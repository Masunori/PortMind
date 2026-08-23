"""Generate bounded scenario assumptions through the AI provider interface."""

import re

from pydantic import BaseModel, Field

from app.ai import AIProvider
from app.domain.disruption import Disruption, DisruptionEffects
from app.domain.exposure import ExposureAnalysis
from app.domain.scenario import Scenario


class ScenarioGenerationContext(BaseModel):
    """Provide grounded disruption and exposure context to generation."""

    disruption: Disruption
    exposure: ExposureAnalysis


class ScenarioProposal(BaseModel):
    """Represent one AI-proposed but not yet accepted scenario assumption."""

    name: str = Field(min_length=1)
    probability: float = Field(ge=0, le=1)
    duration_hours: float = Field(gt=0, le=24 * 365)
    severity_multiplier: float = Field(gt=0, le=10)


class ScenarioProposalBatch(BaseModel):
    """Wrap scenario proposals for structured provider generation."""

    proposals: list[ScenarioProposal] = Field(min_length=1, max_length=20)


def _slug(value: str) -> str:
    """Create a stable identifier component from a proposal name."""

    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _scenario_effects(
    disruption: Disruption,
    severity_multiplier: float,
) -> DisruptionEffects:
    """Apply proposal severity to the disruption's supported effect type."""

    effects = disruption.effects
    updates: dict[str, object] = {}
    if effects.handling_time_multiplier is not None:
        updates["handling_time_multiplier"] = severity_multiplier
    elif effects.transit_time_multiplier is not None:
        updates["transit_time_multiplier"] = severity_multiplier
    elif effects.capacity_multiplier is not None:
        updates["capacity_multiplier"] = min(1, 1 / severity_multiplier)
    elif effects.node_handling_delay_hours is not None:
        updates["node_handling_delay_hours"] = (
            effects.node_handling_delay_hours * severity_multiplier
        )
    elif effects.edge_disabled:
        updates["edge_disabled"] = True
    else:
        raise ValueError("Disruption has no scenario-compatible effect")
    return effects.model_copy(update=updates)


def validate_and_convert_proposals(
    context: ScenarioGenerationContext,
    batch: ScenarioProposalBatch,
) -> list[Scenario]:
    """Normalize probabilities and convert validated assumptions to scenarios."""

    probability_total = sum(proposal.probability for proposal in batch.proposals)
    if probability_total <= 0:
        raise ValueError("Scenario probabilities must have a positive total")
    if not context.exposure.affected_nodes and not context.exposure.affected_edges:
        raise ValueError("Cannot generate scenarios without grounded exposure")

    scenario_names: set[str] = set()
    scenarios: list[Scenario] = []
    for index, proposal in enumerate(batch.proposals, 1):
        name_slug = _slug(proposal.name)
        if not name_slug:
            raise ValueError("Scenario name must contain letters or numbers")
        if name_slug in scenario_names:
            raise ValueError(f"Duplicate scenario name: {proposal.name}")
        scenario_names.add(name_slug)
        identifier = f"generated-{index}-{name_slug}"
        disruption = context.disruption.model_copy(
            update={
                "id": f"{identifier}-disruption",
                "start_time": 0,
                "end_time": proposal.duration_hours,
                "effects": _scenario_effects(
                    context.disruption,
                    proposal.severity_multiplier,
                ),
            }
        )
        scenarios.append(
            Scenario(
                id=identifier,
                name=proposal.name,
                probability=proposal.probability / probability_total,
                disruptions=[disruption],
            )
        )
    return scenarios


class ScenarioGenerator:
    """Ask an abstract provider for assumptions, then validate in Python."""

    def __init__(self, provider: AIProvider) -> None:
        """Initialize the generator with its provider dependency."""

        self._provider = provider

    async def generate(
        self,
        context: ScenarioGenerationContext,
    ) -> list[Scenario]:
        """Generate, validate, normalize, and convert scenario proposals."""

        prompt = (
            f"Generate scenarios for {context.disruption.type.value}; "
            f"affected nodes: {', '.join(context.exposure.affected_nodes)}; "
            f"affected shipments: {len(context.exposure.affected_shipments)}"
        )
        batch = await self._provider.structured_generate(
            prompt,
            ScenarioProposalBatch,
        )
        return validate_and_convert_proposals(context, batch)
