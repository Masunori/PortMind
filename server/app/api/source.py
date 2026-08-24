"""HTTP CRUD endpoints for ingestion sources."""

from fastapi import APIRouter, HTTPException, Response, status

from app.domain.source import DataSource, DataSourceCreate, DataSourceUpdate
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

    if not delete_source(source_id):
        raise HTTPException(status_code=404, detail="Source not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
