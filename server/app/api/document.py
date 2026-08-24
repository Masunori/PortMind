"""Raw-document browsing, upload, and manual collection endpoints."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.domain.document import DocumentCreate, DocumentStoreResult, RawDocument
from app.domain.source import DataSourceCreate, SourceCollectionResult, SourceType
from app.ingestion.discovery import discover_and_scrape_source
from app.ingestion.extractors import extract_upload
from app.services.document_service import get_document, get_documents, store_document
from app.services.source_service import (
    create_source,
    get_source,
    get_sources,
    record_source_run,
)

router = APIRouter(tags=["documents"])
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _upload_source(source_id: str | None):
    """Resolve an explicit upload source or create the shared default source."""

    if source_id:
        source = get_source(source_id)
        if source is None or source.type is not SourceType.UPLOAD:
            raise HTTPException(status_code=400, detail="Upload source not found")
        return source
    existing = next(
        (item for item in get_sources() if item.type is SourceType.UPLOAD), None
    )
    return existing or create_source(
        DataSourceCreate(name="Uploaded documents", type=SourceType.UPLOAD)
    )


@router.get("/api/documents", response_model=list[RawDocument])
def documents(source_id: str | None = None) -> list[RawDocument]:
    """List collected documents, optionally for one source."""

    return get_documents(source_id)


@router.get("/api/documents/{document_id}", response_model=RawDocument)
def document(document_id: str) -> RawDocument:
    """Return one collected document."""

    result = get_document(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.post(
    "/api/documents/upload",
    response_model=DocumentStoreResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...), source_id: str | None = Form(default=None)
) -> DocumentStoreResult:
    """Extract and store a bounded TXT, PDF, or DOCX upload."""

    value = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(value) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds 10 MB")
    try:
        content = extract_upload(file.filename or "document", file.content_type or "", value)
    except (ValueError, UnicodeError) as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    if not content.strip():
        raise HTTPException(status_code=422, detail="Document contains no extractable text")
    source = _upload_source(source_id)
    document, created = store_document(
        DocumentCreate(
            source_id=source.id,
            title=file.filename or "Uploaded document",
            media_type=file.content_type or "application/octet-stream",
            content=content,
        )
    )
    return DocumentStoreResult(document=document, created=created)


@router.post("/api/sources/{source_id}/collect", response_model=SourceCollectionResult)
async def collect_source(source_id: str) -> SourceCollectionResult:
    """Run one website source immediately and record its health."""

    source = get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    try:
        result = await discover_and_scrape_source(source)
    except Exception as error:
        record_source_run(source_id, str(error))
        raise HTTPException(status_code=502, detail="Source collection failed") from error
    record_source_run(source_id)
    return result
