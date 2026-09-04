"""Unified evidence inbox and retention lifecycle API."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status

from app.integrations import get_client_gateway, get_provider_bundle
from app.integrations.contracts import CanonicalSignal, DeletionImpact, DuplicateDeletionPreview, DuplicateDeletionResult, Evidence, EvidenceCreate, EvidenceKind, EvidenceProcessingEligibility, EvidenceStoreResult, EvidenceUpdate
from app.integrations.gateway import ClientGateway
from app.integrations.bedrock import BedrockAPIError
from app.integrations.gemini import GeminiAPIError
from app.integrations.providers import ProviderBundle
from app.services.collection_service import process_stored_evidence
from app.services.evidence_service import delete_evidence, delete_unprotected_duplicates, deletion_impact, duplicate_deletion_preview, get_evidence, list_evidence, remove_raw_content, set_archived, store_evidence, update_evidence
from app.services.signal_service import get_evidence_processing_eligibility
from app.ingestion.extractors import extract_upload

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


@router.get("", response_model=list[Evidence])
def inbox(archived: bool | None = False, kind: EvidenceKind | None = None,
          include_duplicates: bool = False,
          limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> list[Evidence]:
    return list_evidence(archived=archived, kind=kind,
                         include_duplicates=include_duplicates,
                         limit=limit, offset=offset)


@router.post("", response_model=EvidenceStoreResult, status_code=status.HTTP_201_CREATED)
def create(values: EvidenceCreate) -> EvidenceStoreResult:
    try: item, duplicate = store_evidence(values)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error
    return EvidenceStoreResult(evidence=item, duplicate=duplicate)


@router.post("/upload", response_model=EvidenceStoreResult, status_code=status.HTTP_201_CREATED)
async def upload(source_id: str = Form(...), file: UploadFile = File(...)) -> EvidenceStoreResult:
    """Extract an uploaded document directly into the canonical evidence store."""

    try:
        content = extract_upload(file.filename or "upload.txt", file.content_type or "application/octet-stream",
                                 await file.read())
        item, duplicate = store_evidence(EvidenceCreate(source_id=source_id, kind=EvidenceKind.UPLOAD,
            title=file.filename or "Upload", media_type=file.content_type or "application/octet-stream",
            content=content))
    except (LookupError, ValueError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return EvidenceStoreResult(evidence=item, duplicate=duplicate)


@router.get("/{evidence_id}", response_model=Evidence)
def detail(evidence_id: str) -> Evidence:
    item = get_evidence(evidence_id)
    if item is None: raise HTTPException(status_code=404, detail="Evidence not found")
    return item


@router.get(
    "/{evidence_id}/processing-eligibility",
    response_model=EvidenceProcessingEligibility,
)
def processing_eligibility(evidence_id: str) -> EvidenceProcessingEligibility:
    """Return retry eligibility and immutable prior-attempt summaries."""

    try:
        return get_evidence_processing_eligibility(evidence_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{evidence_id}/process", response_model=CanonicalSignal | None)
async def retry_processing(
    evidence_id: str,
    gateway: ClientGateway = Depends(get_client_gateway),
    providers: ProviderBundle = Depends(get_provider_bundle),
) -> CanonicalSignal | None:
    """Process stored evidence without scraping its source a second time."""

    item = get_evidence(evidence_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if item.duplicate_of_id is not None:
        raise HTTPException(status_code=409, detail="Process the canonical evidence instead")
    try:
        return await process_stored_evidence(
            evidence_id, gateway=gateway, providers=providers)
    except (BedrockAPIError, GeminiAPIError) as error:
        raise HTTPException(
            status_code=429 if error.status_code == 429 else 503,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{evidence_id}/archive", response_model=Evidence)
def archive(evidence_id: str) -> Evidence:
    try: return set_archived(evidence_id, True)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{evidence_id}/restore", response_model=Evidence)
def restore(evidence_id: str) -> Evidence:
    try: return set_archived(evidence_id, False)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{evidence_id}/deletion-impact", response_model=DeletionImpact)
def preview_deletion(evidence_id: str) -> DeletionImpact:
    try: return deletion_impact(evidence_id)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{evidence_id}/duplicates/deletion-impact", response_model=DuplicateDeletionPreview)
def preview_duplicate_deletion(evidence_id: str) -> DuplicateDeletionPreview:
    try: return duplicate_deletion_preview(evidence_id)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error: raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/{evidence_id}/duplicates", response_model=DuplicateDeletionResult)
def remove_duplicates(evidence_id: str,
                      delete_canonical: bool = False) -> DuplicateDeletionResult:
    try: return delete_unprotected_duplicates(evidence_id, delete_canonical=delete_canonical)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error: raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/{evidence_id}/raw-content", response_model=Evidence)
def redact_raw_content(evidence_id: str) -> Evidence:
    try: return remove_raw_content(evidence_id)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error: raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{evidence_id}", response_model=Evidence)
def edit(evidence_id: str, values: EvidenceUpdate) -> Evidence:
    try: return update_evidence(evidence_id, values)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error: raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(evidence_id: str) -> Response:
    try: delete_evidence(evidence_id)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error: raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
