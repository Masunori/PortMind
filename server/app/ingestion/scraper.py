"""Manual website collection through an injectable HTTP transport."""

import httpx

from app.domain.document import DocumentCreate, RawDocument
from app.domain.source import DataSource, SourceType
from app.ingestion.extractors import extract_html
from app.services.document_service import store_document


async def scrape_source(
    source: DataSource,
    client: httpx.AsyncClient | None = None,
) -> tuple[RawDocument, bool]:
    """Fetch, extract, and deduplicate one configured website source."""

    if source.type is not SourceType.WEBSITE or source.url is None:
        raise ValueError("Only website sources can be scraped")
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=20, follow_redirects=True)
    try:
        response = await active_client.get(source.url)
        response.raise_for_status()
        title, content = extract_html(response.text)
        return store_document(
            DocumentCreate(
                source_id=source.id,
                title=title,
                source_url=str(response.url),
                media_type=response.headers.get("content-type", "text/html"),
                content=content,
            )
        )
    finally:
        if owns_client:
            await active_client.aclose()
