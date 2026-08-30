"""Canonical signal processing and human review endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.integrations import get_client_gateway, get_provider_bundle
from app.integrations.contracts import CanonicalSignal
from app.integrations.errors import ClientGatewayError
from app.integrations.gateway import ClientGateway
from app.integrations.providers import ProviderBundle
from app.services.signal_service import get_signal_version, list_signals, process_evidence, relate_signals, review_signal

router = APIRouter(prefix="/api/signals", tags=["signals"])


class ReviewRequest(BaseModel):
    """Capture a human review decision for a canonical signal."""

    decision: str


class RelationshipCreate(BaseModel):
    """Select the second signal version for relationship inference."""

    target_version_id: str


@router.get("", response_model=list[CanonicalSignal])
def index(review_status: str | None = None,
          limit: int = Query(50, ge=1, le=200),
          offset: int = Query(0, ge=0)) -> list[CanonicalSignal]:
    """List current signal versions for the human-review workspace."""

    return list_signals(review_status=review_status, limit=limit, offset=offset)


@router.post("/from-evidence/{evidence_id}", response_model=CanonicalSignal | None)
async def from_evidence(evidence_id: str, gateway: ClientGateway = Depends(get_client_gateway),
                        providers: ProviderBundle = Depends(get_provider_bundle)) -> CanonicalSignal | None:
    try: return await process_evidence(evidence_id, gateway=gateway, providers=providers)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error: raise HTTPException(status_code=409, detail=str(error)) from error
    except ClientGatewayError as error: raise HTTPException(status_code=502, detail={"code": error.code, "message": str(error)}) from error


@router.get("/versions/{version_id}", response_model=CanonicalSignal)
def version(version_id: str) -> CanonicalSignal:
    try: return get_signal_version(version_id)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{signal_id}/review", response_model=CanonicalSignal)
def review(signal_id: str, request: ReviewRequest) -> CanonicalSignal:
    try: return review_signal(signal_id, request.decision)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error: raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/versions/{source_version_id}/relationships")
async def relationship(source_version_id: str, request: RelationshipCreate,
                       providers: ProviderBundle = Depends(get_provider_bundle)) -> dict[str, object] | None:
    try: return await relate_signals(source_version_id, request.target_version_id, providers=providers)
    except LookupError as error: raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error: raise HTTPException(status_code=409, detail=str(error)) from error
