"""HTTP endpoint for deterministic baseline simulations."""

from fastapi import APIRouter, HTTPException, Query

from app.services.disruption_service import get_disruptions
from app.services.network_service import get_network, get_shipments
from app.simulation import SimulationResult, simulate

router = APIRouter(prefix="/api", tags=["simulations"])


@router.post("/simulations", response_model=SimulationResult)
def run_simulation(
    horizon_hours: float = Query(default=168, gt=0),
) -> SimulationResult:
    """Run the persisted network through the deterministic simulation engine."""

    try:
        return simulate(
            network=get_network(),
            shipments=get_shipments(),
            horizon_hours=horizon_hours,
            disruptions=get_disruptions(enabled_only=True),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
