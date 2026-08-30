"""Independent due-source scheduling without provider-specific infrastructure."""

from collections.abc import Awaitable, Callable
from datetime import datetime

from app.domain.source import DataSource, SourceCollectionResult
from app.integrations import get_client_gateway, get_provider_bundle
from app.integrations.gateway import ClientGateway
from app.integrations.providers import ProviderBundle
from app.services.collection_service import collect_and_process_source
from app.services.source_service import get_due_sources, record_source_run

Collector = Callable[[DataSource, ClientGateway, ProviderBundle], Awaitable[object]]


async def _default_collector(
    source: DataSource,
    gateway: ClientGateway,
    providers: ProviderBundle,
) -> object:
    return await collect_and_process_source(source, gateway=gateway, providers=providers)


async def collect_due_sources(
    now: datetime | None = None,
    collector: Collector = _default_collector,
    gateway: ClientGateway | None = None,
    providers: ProviderBundle | None = None,
) -> int:
    """Collect and process every due source while persisting per-source health."""

    due = get_due_sources(now)
    if not due:
        return 0
    active_gateway = gateway or get_client_gateway()
    active_providers = providers or get_provider_bundle()
    for source in due:
        try:
            result = await collector(source, active_gateway, active_providers)
        except Exception as error:  # collection failures must not block other sources
            record_source_run(source.id, str(error))
        else:
            processing_error = None
            if isinstance(result, SourceCollectionResult) and result.processing.failed:
                processing_error = (
                    f"{result.processing.failed} evidence item(s) failed processing unexpectedly"
                )
            record_source_run(source.id, processing_error)
    return len(due)
