"""HTTP endpoints for network and shipment queries."""

from fastapi import APIRouter

from app.domain.network import Network
from app.domain.shipment import Shipment
from app.services.network_service import get_network, get_shipments

router = APIRouter(prefix="/api", tags=["network"])


@router.get("/network", response_model=Network)
def network() -> Network:
    """Return the persisted supply-chain network."""

    return get_network()


@router.get("/shipments", response_model=list[Shipment])
def shipments() -> list[Shipment]:
    """Return all persisted shipments."""

    return get_shipments()
