"""Tests for source validation, persistence, and HTTP behavior."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api import source as source_api
from app.domain.source import (
    DataSourceCreate,
    DataSourceUpdate,
    SourceCollectionResult,
    SourceProcessingError,
    SourceProcessingSummary,
    SourceType,
)
from app.integrations.contracts import EvidenceCreate, EvidenceKind
from app.integrations.gemini import GeminiRateLimitError
from app.services import collection_service
from app.services import scheduler_service
from app.services.evidence_service import store_evidence
from app.services.source_service import (
    create_source,
    delete_source,
    get_source,
    get_sources,
    update_source,
)


def website(name: str = "Port notices", interval: int = 30) -> DataSourceCreate:
    """Build one valid website source request."""

    return DataSourceCreate(
        name=name,
        type=SourceType.WEBSITE,
        url="https://example.com/notices",
        scrape_interval_minutes=interval,
        scraper_type="HTML",
    )


def run(value):
    return asyncio.run(value)


def test_source_type_specific_validation() -> None:
    """Website fields are required and uploads reject scraper configuration."""

    with pytest.raises(ValidationError, match=r"HTTP\(S\) URL"):
        DataSourceCreate(name="Broken", type=SourceType.WEBSITE)
    with pytest.raises(ValidationError, match="cannot contain scraper"):
        DataSourceCreate(
            name="Uploads",
            type=SourceType.UPLOAD,
            url="https://example.com",
        )
    with pytest.raises(ValidationError, match="less than or equal to 5"):
        DataSourceCreate(
            name="Unbounded",
            type=SourceType.WEBSITE,
            url="https://example.com",
            scrape_interval_minutes=30,
            scraper_type="HTML",
            scraper_config_json={"enabled": True, "max_depth": 6},
        )


def test_discovery_configuration_is_normalized() -> None:
    """Keywords are normalized and bounded settings survive source validation."""

    values = DataSourceCreate(
        name="News",
        type=SourceType.WEBSITE,
        url="https://example.com",
        scrape_interval_minutes=30,
        scraper_type="HTML",
        scraper_config_json={
            "enabled": True,
            "mode": "AUTO",
            "max_depth": 3,
            "keywords": [" Port ", "port", "Typhoon"],
        },
    )
    assert values.scraper_config_json is not None
    assert values.scraper_config_json["max_depth"] == 3
    assert values.scraper_config_json["keywords"] == ["port", "typhoon"]


def test_source_crud_and_independent_schedules(test_session_factory) -> None:
    """Sources retain independent schedules and support the complete lifecycle."""

    fast = create_source(website("Fast", 10))
    slow = create_source(website("Slow", 30))

    assert [item.name for item in get_sources()] == ["Fast", "Slow"]
    assert fast.next_run_at is not None
    assert slow.next_run_at is not None
    delta = slow.next_run_at - fast.next_run_at
    assert timedelta(minutes=19, seconds=59) < delta < timedelta(minutes=20, seconds=1)

    updated = update_source(fast.id, DataSourceUpdate(enabled=False))
    assert updated is not None
    assert updated.enabled is False
    assert updated.next_run_at is None
    persisted = get_source(fast.id)
    assert persisted is not None
    assert persisted.enabled is False
    assert persisted.next_run_at is None
    assert delete_source(fast.id) is True
    assert delete_source(fast.id) is False


def test_source_update_revalidates_website_configuration(test_session_factory) -> None:
    """Partial edits cannot leave a website source in an invalid state."""

    source = create_source(website())
    with pytest.raises(ValidationError, match=r"HTTP\(S\) URL"):
        update_source(source.id, DataSourceUpdate(url=None))


def test_source_update_replaces_complete_scraper_configuration(
    test_session_factory,
) -> None:
    """A website edit persists schedule, URL, and every discovery control."""

    source = create_source(website())
    updated = update_source(
        source.id,
        DataSourceUpdate(
            name="Updated notices",
            description="Maritime alerts",
            url="https://example.com/news",
            scrape_interval_minutes=90,
            scraper_config_json={
                "enabled": True,
                "mode": "RSS",
                "max_depth": 3,
                "max_pages": 75,
                "keywords": ["Port", "Typhoon"],
                "allowed_paths": ["/news/"],
                "excluded_paths": ["/news/archive/"],
                "feed_url": "https://example.com/news/feed.xml",
                "sitemap_url": "https://example.com/news-sitemap.xml",
            },
        ),
    )
    assert updated is not None
    assert updated.name == "Updated notices"
    assert updated.description == "Maritime alerts"
    assert updated.url == "https://example.com/news"
    assert updated.scrape_interval_minutes == 90
    assert updated.scraper_config_json is not None
    assert updated.scraper_config_json["keywords"] == ["port", "typhoon"]
    assert updated.scraper_config_json["feed_url"].endswith("feed.xml")
    assert updated.next_run_at is not None
    assert updated.updated_at is not None
    assert timedelta(minutes=89, seconds=59) < (
        updated.next_run_at - updated.updated_at
    ) < timedelta(minutes=90, seconds=1)


def test_source_api_crud(test_session_factory) -> None:
    """The management API returns useful statuses for create, edit, and delete."""

    result = source_api.add_source(
        DataSourceCreate.model_validate({
            "name": "Weather alerts",
            "type": "WEBSITE",
            "url": "https://example.com/weather",
            "scrape_interval_minutes": 15,
            "scraper_type": "HTML",
        })
    )
    assert source_api.sources()[0].name == "Weather alerts"
    assert source_api.edit_source(
        result.id, DataSourceUpdate(enabled=False)
    ).next_run_at is None
    assert source_api.remove_source(result.id).status_code == 204
    with pytest.raises(Exception) as error:
        source_api.source(result.id)
    assert error.value.status_code == 404


def test_collection_processes_new_evidence_and_skips_duplicates(
    test_session_factory, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scrape hands each original evidence item to the signal pipeline once."""

    source = create_source(website())
    original, _ = store_evidence(EvidenceCreate(
        source_id=source.id, kind=EvidenceKind.WEBSITE, title="Port alert",
        media_type="text/plain", content="Hai Phong port may close tomorrow",
    ))
    duplicate, is_duplicate = store_evidence(EvidenceCreate(
        source_id=source.id, kind=EvidenceKind.WEBSITE, title="Copied alert",
        media_type="text/plain", content="Hai Phong port may close tomorrow",
    ))
    assert is_duplicate is True
    collection = SourceCollectionResult(
        source_id=source.id, evidence=[original, duplicate], discovered_urls=2,
        fetched_pages=2, skipped_urls=0, created_evidence=1, duplicate_evidence=1,
    )
    processed: list[str] = []

    async def collect(_source):
        return collection

    async def process(evidence_id, **_dependencies):
        processed.append(evidence_id)

    monkeypatch.setattr(collection_service, "discover_and_scrape_source", collect)
    monkeypatch.setattr(collection_service, "process_evidence", process)

    result = run(collection_service.collect_and_process_source(
        source, gateway=object(), providers=object(),
    ))

    assert processed == [original.id]
    assert result.errors == []
    assert result.processing.attempted == 1
    assert result.processing.filtered_out == 1


@pytest.mark.parametrize(
    ("outcome", "field"),
    [
        ("READY_FOR_REVIEW", "ready_for_review"),
        (None, "filtered_out"),
        ("NEEDS_RESOLUTION", "needs_resolution"),
        ("MAPPING_FAILED", "mapping_failed"),
    ],
)
def test_collection_summarizes_processing_outcomes(
    test_session_factory,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str | None,
    field: str,
) -> None:
    """Each supported terminal outcome is counted without becoming an error."""

    source = create_source(website())
    evidence, _ = store_evidence(EvidenceCreate(
        source_id=source.id, kind=EvidenceKind.WEBSITE, title="Notice",
        media_type="text/plain", content=f"Unique notice for {outcome}",
    ))
    collection = SourceCollectionResult(
        source_id=source.id, evidence=[evidence], discovered_urls=1,
        fetched_pages=1, skipped_urls=0, created_evidence=1, duplicate_evidence=0,
        errors=["one page could not be fetched"],
    )

    async def collect(_source):
        return collection

    async def process(_evidence_id, **_dependencies):
        return None if outcome is None else SimpleNamespace(processing_state=outcome)

    monkeypatch.setattr(collection_service, "discover_and_scrape_source", collect)
    monkeypatch.setattr(collection_service, "process_evidence", process)
    result = run(collection_service.collect_and_process_source(
        source, gateway=object(), providers=object(),
    ))

    assert result.processing.attempted == 1
    assert getattr(result.processing, field) == 1
    assert result.processing.failed == 0
    assert result.processing.errors == []
    assert result.errors == ["one page could not be fetched"]


def test_collection_records_failure_and_continues(
    test_session_factory, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpected item failure is safe, separate, and does not stop later items."""

    source = create_source(website())
    first, _ = store_evidence(EvidenceCreate(
        source_id=source.id, kind=EvidenceKind.WEBSITE, title="First",
        media_type="text/plain", content="First unique processing failure",
    ))
    second, _ = store_evidence(EvidenceCreate(
        source_id=source.id, kind=EvidenceKind.WEBSITE, title="Second",
        media_type="text/plain", content="Second unique processing success",
    ))
    collection = SourceCollectionResult(
        source_id=source.id, evidence=[first, second], discovered_urls=2,
        fetched_pages=2, skipped_urls=0, created_evidence=2, duplicate_evidence=0,
        errors=["discovery warning"],
    )
    calls: list[str] = []
    logged: list[tuple[str, str]] = []

    async def collect(_source):
        return collection

    async def process(evidence_id, **_dependencies):
        calls.append(evidence_id)
        if evidence_id == first.id:
            raise RuntimeError("provider credential must not reach the browser")
        return SimpleNamespace(processing_state="READY_FOR_REVIEW")

    monkeypatch.setattr(collection_service, "discover_and_scrape_source", collect)
    monkeypatch.setattr(collection_service, "process_evidence", process)
    monkeypatch.setattr(collection_service.logger, "exception",
        lambda message, evidence_id: logged.append((message, evidence_id)))
    result = run(collection_service.collect_and_process_source(
        source, gateway=object(), providers=object(),
    ))

    assert calls == [first.id, second.id]
    assert result.processing.attempted == 2
    assert result.processing.ready_for_review == 1
    assert result.processing.failed == 1
    assert result.processing.errors == [SourceProcessingError(
        evidence_id=first.id, message="Processing failed unexpectedly",
    )]
    assert result.errors == ["discovery warning"]
    assert logged == [("Unexpected failure processing evidence %s", first.id)]


def test_collection_defers_remaining_items_after_exhausted_gemini_quota(
    test_session_factory, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One shared quota failure avoids repeatedly calling Gemini for the batch."""

    source = create_source(website())
    items = [store_evidence(EvidenceCreate(
        source_id=source.id, kind=EvidenceKind.WEBSITE, title=f"Item {index}",
        media_type="text/plain", content=f"Unique quota item {index}",
    ))[0] for index in range(3)]
    collection = SourceCollectionResult(
        source_id=source.id, evidence=items, discovered_urls=3,
        fetched_pages=3, skipped_urls=0, created_evidence=3,
        duplicate_evidence=0,
    )
    calls = []

    async def collect(_source):
        return collection

    async def process(evidence_id, **_dependencies):
        calls.append(evidence_id)
        raise GeminiRateLimitError(
            "Gemini rate limit or quota exhausted: minute quota",
            status_code=429, retryable=True,
        )

    monkeypatch.setattr(collection_service, "discover_and_scrape_source", collect)
    monkeypatch.setattr(collection_service, "process_evidence", process)
    result = run(collection_service.collect_and_process_source(
        source, gateway=object(), providers=object(),
    ))

    assert calls == [items[0].id]
    assert result.processing.attempted == 1
    assert result.processing.deferred == 3
    assert result.processing.failed == 0
    assert len(result.processing.errors) == 3
    assert "quota exhausted" in result.processing.errors[0].message
    assert "deferred" in result.processing.errors[1].message.casefold()


def test_collection_treats_unknown_processing_state_as_failure(
    test_session_factory, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new unsupported state is visible instead of silently disappearing."""

    source = create_source(website())
    evidence, _ = store_evidence(EvidenceCreate(
        source_id=source.id, kind=EvidenceKind.WEBSITE, title="Unknown",
        media_type="text/plain", content="Unique unknown processing state",
    ))
    collection = SourceCollectionResult(
        source_id=source.id, evidence=[evidence], discovered_urls=1,
        fetched_pages=1, skipped_urls=0, created_evidence=1, duplicate_evidence=0,
    )

    async def collect(_source): return collection
    async def process(_evidence_id, **_dependencies):
        return SimpleNamespace(processing_state="INTERPRETED")

    monkeypatch.setattr(collection_service, "discover_and_scrape_source", collect)
    monkeypatch.setattr(collection_service, "process_evidence", process)
    result = run(collection_service.collect_and_process_source(
        source, gateway=object(), providers=object(),
    ))
    assert result.processing.failed == 1
    assert result.processing.errors[0].evidence_id == evidence.id
    assert "INTERPRETED" in result.processing.errors[0].message


def test_scheduler_retains_unexpected_processing_failure(
    test_session_factory, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduled processing exceptions affect health while normal outcomes do not."""

    source = create_source(website())
    recorded: list[tuple[str, str | None]] = []
    monkeypatch.setattr(scheduler_service, "get_due_sources", lambda _now: [source])
    monkeypatch.setattr(
        scheduler_service, "record_source_run",
        lambda source_id, error=None: recorded.append((source_id, error)),
    )

    async def collector(_source, _gateway, _providers):
        return SourceCollectionResult(
            source_id=source.id, evidence=[], discovered_urls=0, fetched_pages=0,
            skipped_urls=0, created_evidence=0, duplicate_evidence=0,
            processing=SourceProcessingSummary(failed=1, errors=[
                SourceProcessingError(evidence_id="evidence-1", message="safe failure")
            ]),
        )

    count = run(scheduler_service.collect_due_sources(
        collector=collector, gateway=object(), providers=object(),
    ))
    assert count == 1
    assert recorded == [(source.id, "1 evidence item(s) failed processing unexpectedly")]
