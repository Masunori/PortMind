"""Tests for provider-assisted, deterministically validated scenarios."""

import asyncio

import pytest
from pydantic import ValidationError

from app.agents.scenario_generator import (
    ScenarioGenerationContext,
    ScenarioGenerator,
    ScenarioProposal,
    ScenarioProposalBatch,
    validate_and_convert_proposals,
)
from app.ai import MockAIProvider
from app.domain.disruption import Disruption, DisruptionEffects, DisruptionType
from app.domain.exposure import ExposureAnalysis


def generation_context() -> ScenarioGenerationContext:
    """Build grounded disruption context for scenario generation tests."""

    disruption = Disruption(
        id="hai-phong-weather",
        type=DisruptionType.PORT_CONGESTION,
        affected_node_ids=["hai-phong-port"],
        start_time=0,
        end_time=48,
        effects=DisruptionEffects(handling_time_multiplier=2),
    )
    return ScenarioGenerationContext(
        disruption=disruption,
        exposure=ExposureAnalysis(
            disruption_id=disruption.id,
            affected_nodes=["hai-phong-port"],
            affected_edges=["02-hai-phong-to-psa"],
            affected_shipments=["shipment-001", "shipment-002"],
            affected_customers=["customer"],
        ),
    )


def test_mock_generator_returns_four_normalized_domain_scenarios() -> None:
    """Mock assumptions become four typed scenarios with a unit probability sum."""

    scenarios = asyncio.run(
        ScenarioGenerator(MockAIProvider()).generate(generation_context())
    )

    assert [scenario.name for scenario in scenarios] == [
        "24h closure",
        "48h closure",
        "72h closure",
        "120h closure",
    ]
    assert sum(scenario.probability for scenario in scenarios) == pytest.approx(1)
    assert [scenario.disruptions[0].end_time for scenario in scenarios] == [
        24,
        48,
        72,
        120,
    ]
    assert all(
        scenario.disruptions[0].effects.handling_time_multiplier == 2
        for scenario in scenarios
    )


def test_python_normalizes_provider_probabilities() -> None:
    """Provider weights need not already sum to one."""

    batch = ScenarioProposalBatch(
        proposals=[
            ScenarioProposal(
                name="Short",
                probability=0.6,
                duration_hours=24,
                severity_multiplier=1.5,
            ),
            ScenarioProposal(
                name="Long",
                probability=0.6,
                duration_hours=48,
                severity_multiplier=2,
            ),
        ]
    )

    scenarios = validate_and_convert_proposals(generation_context(), batch)

    assert [scenario.probability for scenario in scenarios] == [0.5, 0.5]


def test_python_rejects_zero_probability_total() -> None:
    """A provider cannot create a distribution with no probability mass."""

    batch = ScenarioProposalBatch(
        proposals=[
            ScenarioProposal(
                name="Impossible",
                probability=0,
                duration_hours=24,
                severity_multiplier=2,
            )
        ]
    )

    with pytest.raises(ValueError, match="positive total"):
        validate_and_convert_proposals(generation_context(), batch)


def test_python_rejects_ungrounded_scenario_context() -> None:
    """Scenario assumptions cannot proceed without grounded exposure."""

    context = generation_context().model_copy(
        update={
            "exposure": ExposureAnalysis(
                disruption_id="none",
                affected_nodes=[],
                affected_edges=[],
                affected_shipments=[],
                affected_customers=[],
            )
        }
    )
    batch = ScenarioProposalBatch(
        proposals=[
            ScenarioProposal(
                name="24h",
                probability=1,
                duration_hours=24,
                severity_multiplier=2,
            )
        ]
    )

    with pytest.raises(ValueError, match="grounded exposure"):
        validate_and_convert_proposals(context, batch)


@pytest.mark.parametrize(
    ("field", "value"),
    [("duration_hours", 0), ("severity_multiplier", 0), ("probability", 1.1)],
)
def test_proposals_reject_impossible_values(field: str, value: float) -> None:
    """Pydantic rejects impossible generated assumptions before conversion."""

    values = {
        "name": "Invalid",
        "probability": 1,
        "duration_hours": 24,
        "severity_multiplier": 2,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        ScenarioProposal(**values)
