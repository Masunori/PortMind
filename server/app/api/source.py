"""HTTP CRUD endpoints for ingestion sources."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.domain.source import DataSource, DataSourceCreate, DataSourceUpdate, SourceCollectionResult
from app.integrations import get_client_gateway, get_provider_bundle
from app.integrations.gateway import ClientGateway
from app.integrations.providers import ProviderBundle
from app.services.collection_service import collect_and_process_source
from app.services.source_service import (
    create_source,
    delete_source,
    get_source,
    get_sources,
    update_source,
)

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[DataSource])
def sources() -> list[DataSource]:
    """List configured ingestion sources."""

    return get_sources()


@router.post("", response_model=DataSource, status_code=status.HTTP_201_CREATED)
def add_source(values: DataSourceCreate) -> DataSource:
    """Create an independently configured ingestion source."""

    return create_source(values)


@router.get("/{source_id}", response_model=DataSource)
def source(source_id: str) -> DataSource:
    """Return one configured source."""

    result = get_source(source_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return result


@router.patch("/{source_id}", response_model=DataSource)
def edit_source(source_id: str, values: DataSourceUpdate) -> DataSource:
    """Update source state or collection configuration."""

    result = update_source(source_id, values)
    if result is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return result


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_source(source_id: str) -> Response:
    """Delete a source or return HTTP 404."""

    try:
        removed = delete_source(source_id)
    except PermissionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not removed: raise HTTPException(status_code=404, detail="Source not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{source_id}/collect", response_model=SourceCollectionResult)
async def collect_source(
    source_id: str,
    gateway: ClientGateway = Depends(get_client_gateway),
    providers: ProviderBundle = Depends(get_provider_bundle),
) -> SourceCollectionResult:
    """Collect a configured website and process its newly created evidence."""

    item = get_source(source_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Source not found")
    try:
        return await collect_and_process_source(item, gateway=gateway, providers=providers)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
