"""Tests for source validation, persistence, and HTTP behavior."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.api import source as source_api
from app.domain.source import DataSourceCreate, DataSourceUpdate, SourceType
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
