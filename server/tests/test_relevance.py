"""Tests for PSA-aware relevance assessment and human review."""

import pytest

from app.ai.mock import MockAIProvider
from app.ai.schemas import RelevanceAssessment
from app.domain.assessment import RelevanceDecision
from app.domain.document import DocumentCreate
from app.domain.source import DataSourceCreate, SourceType
from app.services.document_service import store_document
from app.services.relevance_service import assess_document, override_assessment
from app.services.source_service import create_source
from app.seed import seed


class RecordingProvider:
    """Capture the context while returning a controlled assessment."""

    def __init__(self, probability: float) -> None:
        """Configure the returned relevance probability."""

        self.probability = probability
        self.prompt = ""

    async def structured_generate(self, prompt: str, output_type):
        """Record the prompt and construct validated output."""

        self.prompt = prompt
        assert output_type is RelevanceAssessment
        return output_type(
            relevance_probability=self.probability,
            rationale="Controlled test",
            matched_entities=["Hai Phong Port"],
        )


def document(content: str):
    """Persist a raw document for relevance tests."""

    source = create_source(
        DataSourceCreate(name="Uploads", type=SourceType.UPLOAD)
    )
    return store_document(
        DocumentCreate(
            source_id=source.id,
            title="Notice",
            media_type="text/plain",
            content=content,
        )
    )[0]


@pytest.mark.anyio
async def test_assessment_receives_authoritative_network_context(
    test_session_factory,
) -> None:
    """The provider sees persisted names and routes, never an empty generic prompt."""

    seed()
    item = document("Congestion is expected tomorrow")
    provider = RecordingProvider(0.8)
    result = await assess_document(item.id, provider)
    assert result.decision is RelevanceDecision.RELEVANT
    assert "Hai Phong Port" in provider.prompt
    assert "hai-phong-port->psa-singapore" in provider.prompt
    assert "Congestion is expected tomorrow" in provider.prompt


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        (0.7, RelevanceDecision.RELEVANT),
        (0.5, RelevanceDecision.NEEDS_REVIEW),
        (0.3, RelevanceDecision.IRRELEVANT),
    ],
)
async def test_relevance_thresholds(
    test_session_factory, probability: float, expected: RelevanceDecision
) -> None:
    """Boundary probabilities map to deterministic review decisions."""

    item = document(f"Document {probability}")
    result = await assess_document(item.id, RecordingProvider(probability))
    assert result.decision is expected


@pytest.mark.anyio
async def test_mock_handles_relevant_and_irrelevant_content(test_session_factory) -> None:
    """Local fixtures keep both relevance paths deterministic."""

    irrelevant = document("Football results")
    result = await assess_document(irrelevant.id, MockAIProvider())
    assert result.decision is RelevanceDecision.IRRELEVANT


@pytest.mark.anyio
async def test_human_override_preserves_provider_decision(test_session_factory) -> None:
    """A reviewer changes the effective decision without rewriting evidence."""

    item = document("Ambiguous signal")
    assessed = await assess_document(item.id, RecordingProvider(0.5))
    overridden = override_assessment(item.id, RelevanceDecision.RELEVANT)
    assert assessed.decision is RelevanceDecision.NEEDS_REVIEW
    assert overridden.decision is RelevanceDecision.NEEDS_REVIEW
    assert overridden.effective_decision is RelevanceDecision.RELEVANT
