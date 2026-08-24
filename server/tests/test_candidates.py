"""Tests for candidate extraction, grounding, review, grouping, and provenance."""

import pytest

from app.ai.mock import MockAIProvider
from app.ai.schemas import DisruptionExtraction
from app.domain.assessment import RelevanceDecision
from app.domain.candidate import (
    CandidateReviewStatus,
    CandidateUpdate,
    CandidateValidationStatus,
)
from app.domain.document import DocumentCreate
from app.domain.source import DataSourceCreate, SourceType
from app.services.candidate_service import (
    attach_candidate_run,
    confirm_candidate,
    extract_candidate,
    get_candidate_provenance,
    get_candidate_versions,
    reject_candidate,
    update_candidate,
)
from app.services.document_service import store_document
from app.services.disruption_service import get_disruption
from app.services.relevance_service import assess_document, override_assessment
from app.services.source_service import create_source
from app.services.run_service import start_run
from app.domain.run import RunRequest
from app.seed import seed


class ExtractionProvider:
    """Return a controlled candidate extraction."""

    def __init__(self, values: dict[str, object]) -> None:
        """Store fixture values for generation."""

        self.values = values

    async def structured_generate(self, _prompt: str, output_type):
        """Validate controlled fixture values through the requested schema."""

        assert output_type is DisruptionExtraction
        return output_type.model_validate(self.values)


def extraction(**overrides: object) -> dict[str, object]:
    """Build a valid Hai Phong closure extraction fixture."""

    return {
        "disruption_type": "PORT_CLOSURE",
        "affected_locations": ["Port of Hai Phong"],
        "start_time_hours": 0,
        "end_time_hours": 48,
        "probability": 0.85,
        "severity": 0.9,
        "effects": {"edge_disabled": True},
        "summary": "Container handling is suspended.",
        "confidence": 0.91,
        **overrides,
    }


async def relevant_document(content: str = "Hai Phong closes for 48 hours"):
    """Seed the network and persist one effectively relevant document."""

    source = create_source(
        DataSourceCreate(name=f"Feed {content}", type=SourceType.UPLOAD)
    )
    item = store_document(
        DocumentCreate(
            source_id=source.id,
            title="Port notice",
            media_type="text/plain",
            content=content,
        )
    )[0]
    await assess_document(item.id, MockAIProvider())
    override_assessment(item.id, RelevanceDecision.RELEVANT)
    return item


@pytest.mark.anyio
async def test_candidate_is_grounded_validated_and_confirmed(test_session_factory) -> None:
    """Only backend-grounded IDs enter a confirmed deterministic disruption."""

    seed()
    item = await relevant_document()
    candidate = await extract_candidate(item.id, ExtractionProvider(extraction()))
    assert candidate.validation_status is CandidateValidationStatus.VALIDATED
    assert candidate.affected_node_ids == ["hai-phong-port"]
    assert "02-hai-phong-to-psa" in candidate.affected_edge_ids
    assert candidate.event_id is not None

    accepted = confirm_candidate(candidate.id)
    assert accepted.review_status is CandidateReviewStatus.ACCEPTED
    disruption = get_disruption(accepted.confirmed_disruption_id)
    assert disruption is not None
    assert disruption.affected_node_ids == ["hai-phong-port"]
    run = start_run(RunRequest(signal="Container handling is suspended at Hai Phong"))
    attached = attach_candidate_run(candidate.id, run.run_id)
    assert attached.run_id == run.run_id
    assert get_candidate_provenance(candidate.id).run_id == run.run_id


@pytest.mark.anyio
async def test_unknown_location_and_invalid_values_cannot_be_confirmed(
    test_session_factory,
) -> None:
    """Invented targets and invalid probabilities remain isolated candidates."""

    seed()
    item = await relevant_document()
    candidate = await extract_candidate(
        item.id,
        ExtractionProvider(
            extraction(affected_locations=["Invented Port"], probability=1.5)
        ),
    )
    assert candidate.validation_status is CandidateValidationStatus.INVALID
    assert any("Unresolved location" in item for item in candidate.validation_errors)
    assert any("Probability" in item for item in candidate.validation_errors)
    with pytest.raises(ValueError, match="validated"):
        confirm_candidate(candidate.id)


@pytest.mark.anyio
async def test_candidate_edit_creates_history_and_revalidates(test_session_factory) -> None:
    """Operator edits preserve the former state and run validation again."""

    seed()
    item = await relevant_document()
    candidate = await extract_candidate(item.id, ExtractionProvider(extraction()))
    updated = update_candidate(
        candidate.id,
        CandidateUpdate(end_time=72, probability=1.0, summary="Confirmed closure"),
    )
    versions = get_candidate_versions(candidate.id)
    assert updated.end_time == 72
    assert updated.validation_status is CandidateValidationStatus.VALIDATED
    assert len(versions) == 1
    assert versions[0].snapshot["end_time"] == 48


@pytest.mark.anyio
async def test_multiple_documents_group_into_one_event(test_session_factory) -> None:
    """Overlapping reports for the same type and entity share one event."""

    seed()
    first_document = await relevant_document("Authority closure report")
    second_document = await relevant_document("News closure report")
    first = await extract_candidate(
        first_document.id, ExtractionProvider(extraction())
    )
    second = await extract_candidate(
        second_document.id,
        ExtractionProvider(extraction(start_time_hours=24, end_time_hours=72)),
    )
    assert first.event_id == second.event_id


@pytest.mark.anyio
async def test_rejection_and_provenance_are_retained(test_session_factory) -> None:
    """Rejected evidence remains explainable from source through event."""

    seed()
    item = await relevant_document()
    candidate = await extract_candidate(item.id, ExtractionProvider(extraction()))
    rejected = reject_candidate(candidate.id)
    provenance = get_candidate_provenance(candidate.id)
    assert rejected.review_status is CandidateReviewStatus.REJECTED
    assert provenance.source_id
    assert provenance.document_id == item.id
    assert provenance.assessment_decision == "RELEVANT"
    assert provenance.event_id == candidate.event_id
