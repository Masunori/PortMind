"""Independent due-source scheduling without provider-specific infrastructure."""

from collections.abc import Awaitable, Callable
from datetime import datetime

from app.domain.source import DataSource
from app.ingestion.discovery import discover_and_scrape_source
from app.services.source_service import get_due_sources, record_source_run

Collector = Callable[[DataSource], Awaitable[object]]


async def collect_due_sources(
    now: datetime | None = None,
    collector: Collector = discover_and_scrape_source,
) -> int:
    """Collect every due source independently and persist per-source health."""

    due = get_due_sources(now)
    for source in due:
        try:
            await collector(source)
        except Exception as error:  # collection failures must not block other sources
            record_source_run(source.id, str(error))
        else:
            record_source_run(source.id)
    return len(due)
