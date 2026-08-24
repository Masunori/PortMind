"""Versioned entity-schema management endpoints."""

from fastapi import APIRouter, HTTPException

from app.domain.network_management import ChangeImpact, ContextVersion
from app.domain.schema import EntityKind, EntitySchema, SchemaCreate, SchemaVersionCreate
from app.services.context_version_service import get_context_version
from app.services.schema_service import create_schema, create_schema_version, get_schemas, preview_schema_version

router = APIRouter(prefix="/api", tags=["network schemas"])


@router.get("/schemas", response_model=list[EntitySchema])
def schemas(kind: EntityKind | None = None) -> list[EntitySchema]:
    """List current schema versions, optionally filtered by entity kind."""

    return get_schemas(kind)


@router.post("/schemas", response_model=EntitySchema, status_code=201)
def add_schema(values: SchemaCreate) -> EntitySchema:
    """Create a schema with immutable version one."""

    try:
        return create_schema(values)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/schemas/{schema_id}/versions/preview", response_model=ChangeImpact)
def preview_version(schema_id: str, values: SchemaVersionCreate) -> ChangeImpact:
    """Validate and report the impact of a proposed successor version."""

    try:
        return preview_schema_version(schema_id, values)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/schemas/{schema_id}/versions", response_model=EntitySchema)
def add_version(schema_id: str, values: SchemaVersionCreate) -> EntitySchema:
    """Apply a safe successor and migrate entities to it."""

    try:
        return create_schema_version(schema_id, values)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/network/context-version", response_model=ContextVersion)
def context_version() -> ContextVersion:
    """Expose the current canonical AI-context generation."""

    return ContextVersion(version=get_context_version())
