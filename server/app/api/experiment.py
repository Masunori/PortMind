"""Immutable scenario construction and authoritative simulation handoff API."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.integrations import get_client_gateway
from app.integrations.contracts import ExperimentPackage
from app.integrations.errors import ClientGatewayError
from app.integrations.gateway import ClientGateway
from app.services.experiment_service import create_experiment, refresh_results, submit_experiment

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


class ExperimentCreate(BaseModel):
    """Select immutable signal versions for a reproducible experiment."""

    name: str = Field(min_length=1, max_length=200)
    signal_version_ids: list[str] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, LookupError): return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ClientGatewayError): return HTTPException(status_code=502, detail={"code": error.code, "message": str(error)})
    return HTTPException(status_code=409, detail=str(error))


@router.post("", response_model=ExperimentPackage)
async def create(request: ExperimentCreate, gateway: ClientGateway = Depends(get_client_gateway)) -> ExperimentPackage:
    try: return await create_experiment(request.name, request.signal_version_ids, gateway=gateway,
                                        idempotency_key=request.idempotency_key)
    except (LookupError, ValueError, ClientGatewayError) as error: raise _http_error(error) from error


@router.post("/{experiment_id}/submit", response_model=ExperimentPackage)
async def submit(experiment_id: str, gateway: ClientGateway = Depends(get_client_gateway)) -> ExperimentPackage:
    try: return await submit_experiment(experiment_id, gateway=gateway)
    except (LookupError, ValueError, ClientGatewayError) as error: raise _http_error(error) from error


@router.post("/{experiment_id}/refresh-results")
async def results(experiment_id: str, gateway: ClientGateway = Depends(get_client_gateway)) -> dict[str, object]:
    try: return await refresh_results(experiment_id, gateway=gateway)
    except (LookupError, ValueError, RuntimeError, ClientGatewayError) as error: raise _http_error(error) from error
