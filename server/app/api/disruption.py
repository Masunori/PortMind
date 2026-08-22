"""HTTP endpoints for creating and listing disruptions."""

from fastapi import APIRouter, HTTPException, status

from app.domain.disruption import Disruption, DisruptionToggle
from app.domain.exposure import ExposureAnalysis
from app.services.disruption_service import (
    get_disruption,
    get_disruptions,
    save_disruption,
    set_disruption_enabled,
)
from app.services.exposure_service import analyze_exposure

router = APIRouter(prefix="/api", tags=["disruptions"])


@router.post(
    "/disruptions",
    response_model=Disruption,
    status_code=status.HTTP_201_CREATED,
)
def create_disruption(disruption: Disruption) -> Disruption:
    """Persist a new disruption or replace one with the same identifier."""

    return save_disruption(disruption)


@router.get("/disruptions", response_model=list[Disruption])
def disruptions() -> list[Disruption]:
    """Return all persisted disruptions."""

    return get_disruptions()


@router.patch("/disruptions/{disruption_id}", response_model=Disruption)
def toggle_disruption(
    disruption_id: str,
    toggle: DisruptionToggle,
) -> Disruption:
    """Enable or disable one persisted disruption."""

    disruption = set_disruption_enabled(disruption_id, toggle.enabled)
    if disruption is None:
        raise HTTPException(status_code=404, detail="Disruption not found")
    return disruption


@router.get(
    "/disruptions/{disruption_id}/exposure",
    response_model=ExposureAnalysis,
)
def disruption_exposure(disruption_id: str) -> ExposureAnalysis:
    """Analyze structural exposure downstream of one disruption."""

    disruption = get_disruption(disruption_id)
    if disruption is None:
        raise HTTPException(status_code=404, detail="Disruption not found")
    return analyze_exposure(disruption)
