"""Orchestrate source collection through canonical signal processing."""

import logging

from app.domain.source import DataSource, SourceCollectionResult, SourceProcessingError
from app.ingestion.discovery import discover_and_scrape_source
from app.integrations.gateway import ClientGateway
from app.integrations.bedrock import BedrockRateLimitError
from app.integrations.gemini import GeminiRateLimitError
from app.integrations.providers import ProviderBundle
from app.services.signal_service import process_evidence


logger = logging.getLogger(__name__)


async def collect_and_process_source(
    source: DataSource,
    *,
    gateway: ClientGateway,
    providers: ProviderBundle,
) -> SourceCollectionResult:
    """Collect a source and process each newly stored evidence item independently."""

    result = await discover_and_scrape_source(source)
    processable = [item for item in result.evidence if item.duplicate_of_id is None]
    for index, evidence in enumerate(processable):
        result.processing.attempted += 1
        try:
            signal = await process_evidence(
                evidence.id, gateway=gateway, providers=providers
            )
            if signal is None:
                result.processing.filtered_out += 1
            elif signal.processing_state == "READY_FOR_REVIEW":
                result.processing.ready_for_review += 1
            elif signal.processing_state == "NEEDS_RESOLUTION":
                result.processing.needs_resolution += 1
            elif signal.processing_state == "MAPPING_FAILED":
                result.processing.mapping_failed += 1
            else:
                result.processing.failed += 1
                result.processing.errors.append(SourceProcessingError(
                    evidence_id=evidence.id,
                    message=f"Unexpected processing state: {signal.processing_state}",
                ))
        except (BedrockRateLimitError, GeminiRateLimitError) as error:
            logger.warning("Deferring evidence processing after provider rate limit: %s", evidence.id)
            deferred = processable[index:]
            result.processing.deferred += len(deferred)
            result.processing.errors.extend(SourceProcessingError(
                evidence_id=item.id, message=str(error) if item.id == evidence.id
                else "Processing deferred because the model-provider quota is temporarily unavailable",
            ) for item in deferred)
            break
        except Exception:
            logger.exception("Unexpected failure processing evidence %s", evidence.id)
            result.processing.failed += 1
            result.processing.errors.append(SourceProcessingError(
                evidence_id=evidence.id,
                message="Processing failed unexpectedly",
            ))
    return result


async def process_stored_evidence(
    evidence_id: str,
    *,
    gateway: ClientGateway,
    providers: ProviderBundle,
):
    """Retry canonical signal processing without collecting the source again."""

    return await process_evidence(evidence_id, gateway=gateway, providers=providers)
