"""Provider-neutral document relevance review endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from app.ai import get_ai_provider
from app.ai.base import AIProvider
from app.domain.assessment import AssessmentOverride, DocumentAssessment
from app.services.relevance_service import (
    assess_document,
    get_assessment,
    override_assessment,
)

router = APIRouter(prefix="/api/documents", tags=["document assessments"])


@router.post("/{document_id}/assess", response_model=DocumentAssessment)
async def assess(
    document_id: str,
    provider: AIProvider = Depends(get_ai_provider),
) -> DocumentAssessment:
    """Assess one document against the current persisted PSA network."""

    try:
        return await assess_document(document_id, provider)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{document_id}/assessment", response_model=DocumentAssessment)
def assessment(document_id: str) -> DocumentAssessment:
    """Return the latest relevance assessment."""

    result = get_assessment(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return result


@router.patch("/{document_id}/assessment", response_model=DocumentAssessment)
def override(document_id: str, values: AssessmentOverride) -> DocumentAssessment:
    """Set or clear a human relevance override."""

    try:
        return override_assessment(document_id, values.decision)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
