"""Operator review endpoints for grounded disruption candidates."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.ai import get_ai_provider
from app.ai.base import AIProvider
from app.domain.candidate import (
    CandidateProvenance,
    CandidateUpdate,
    CandidateVersion,
    DisruptionCandidate,
)
from app.domain.exposure import ExposureAnalysis
from app.domain.run import RunRequest, RunResponse
from app.services.candidate_service import (
    analyze_candidate_exposure,
    attach_candidate_run,
    confirm_candidate,
    extract_candidate,
    get_candidate,
    get_candidate_provenance,
    get_candidate_versions,
    get_candidates,
    reject_candidate,
    update_candidate,
)
from app.services.run_service import process_run, start_run

router = APIRouter(prefix="/api/disruption-candidates", tags=["disruption candidates"])


@router.get("", response_model=list[DisruptionCandidate])
def candidates() -> list[DisruptionCandidate]:
    """List the operations candidate inbox."""

    return get_candidates()


@router.post("/from-document/{document_id}", response_model=DisruptionCandidate)
async def extract(
    document_id: str,
    provider: AIProvider = Depends(get_ai_provider),
) -> DisruptionCandidate:
    """Extract, ground, validate, and group one relevant document."""

    try:
        return await extract_candidate(document_id, provider)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{candidate_id}", response_model=DisruptionCandidate)
def candidate(candidate_id: str) -> DisruptionCandidate:
    """Return one disruption candidate."""

    result = get_candidate(candidate_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return result


@router.patch("/{candidate_id}", response_model=DisruptionCandidate)
def edit(candidate_id: str, values: CandidateUpdate) -> DisruptionCandidate:
    """Version and revalidate operator edits."""

    try:
        return update_candidate(candidate_id, values)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{candidate_id}/reject", response_model=DisruptionCandidate)
def reject(candidate_id: str) -> DisruptionCandidate:
    """Reject a pending candidate while retaining evidence."""

    try:
        return reject_candidate(candidate_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{candidate_id}/confirm", response_model=DisruptionCandidate)
def confirm(candidate_id: str) -> DisruptionCandidate:
    """Confirm a validated candidate into the existing disruption pipeline."""

    try:
        return confirm_candidate(candidate_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{candidate_id}/versions", response_model=list[CandidateVersion])
def versions(candidate_id: str) -> list[CandidateVersion]:
    """Return candidate edit history."""

    if get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return get_candidate_versions(candidate_id)


@router.get("/{candidate_id}/provenance", response_model=CandidateProvenance)
def provenance(candidate_id: str) -> CandidateProvenance:
    """Explain why a candidate exists and whether it was confirmed."""

    try:
        return get_candidate_provenance(candidate_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{candidate_id}/exposure", response_model=ExposureAnalysis)
def exposure(candidate_id: str) -> ExposureAnalysis:
    """Preview downstream exposure before operator confirmation."""

    try:
        return analyze_candidate_exposure(candidate_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{candidate_id}/confirm-and-run", response_model=RunResponse)
def confirm_and_run(
    candidate_id: str,
    background_tasks: BackgroundTasks,
) -> RunResponse:
    """Confirm evidence and start the existing observable decision pipeline."""

    candidate = get_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    try:
        confirmed = confirm_candidate(candidate_id)
        response = start_run(
            RunRequest(
                signal=(
                    f"{confirmed.summary} Location: "
                    f"{', '.join(confirmed.affected_locations)}"
                )
            )
        )
        attach_candidate_run(candidate_id, response.run_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    background_tasks.add_task(process_run, response.run_id)
    return response
