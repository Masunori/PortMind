"""Tests for extraction, document storage, collection, and scheduling."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
import asyncio

import httpx
import pytest
from docx import Document
from app.api import document as document_api
from app.domain.document import DocumentCreate
from app.domain.source import DataSourceCreate, SourceType
from app.ingestion.extractors import extract_html, extract_upload
from app.ingestion.discovery import (
    canonicalize_url,
    discover_and_scrape_source,
    parse_feed,
    parse_sitemap,
    should_enqueue_link,
)
from app.ingestion.scraper import scrape_source
from app.services.document_service import content_hash, get_documents, store_document
from app.services.scheduler_service import collect_due_sources
from app.scheduler import build_scheduler
from app.services.source_service import create_source, get_source, update_source
from app.domain.source import DataSourceUpdate


def create_website(interval: int = 1):
    """Persist one valid website source for ingestion tests."""

    return create_source(
        DataSourceCreate(
            name="Port notices",
            type=SourceType.WEBSITE,
            url="https://example.com/notices",
            scrape_interval_minutes=interval,
            scraper_type="HTML",
        )
    )


def test_html_extraction_removes_non_content_elements() -> None:
    """HTML extraction retains visible content and removes executable text."""

    title, content = extract_html(
        "<html><head><title>Port alert</title><script>bad()</script></head>"
        "<body><h1>Closure</h1><p>Hai Phong delayed.</p></body></html>"
    )
    assert title == "Port alert"
    assert "Hai Phong delayed." in content
    assert "bad()" not in content


def test_txt_and_docx_extraction() -> None:
    """Supported upload formats produce deterministic plain text."""

    assert extract_upload("notice.txt", "text/plain", b"Port closed") == "Port closed"
    document = Document()
    document.add_paragraph("Weather warning")
    buffer = BytesIO()
    document.save(buffer)
    assert "Weather warning" in extract_upload(
        "notice.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        buffer.getvalue(),
    )
    with pytest.raises(ValueError, match="Only TXT"):
        extract_upload("image.png", "image/png", b"png")


def test_normalized_sha256_deduplicates_per_source(test_session_factory) -> None:
    """Whitespace-only changes do not create repeated source documents."""

    source = create_website()
    first, created = store_document(
        DocumentCreate(
            source_id=source.id,
            title="First",
            media_type="text/plain",
            content="Port   closed\n\nfor weather",
        )
    )
    duplicate, created_again = store_document(
        DocumentCreate(
            source_id=source.id,
            title="Second",
            media_type="text/plain",
            content="Port closed\nfor weather",
        )
    )
    assert created is True
    assert created_again is False
    assert duplicate.id == first.id
    assert first.content_hash == content_hash("Port closed\nfor weather")
    assert len(get_documents(source.id)) == 1


@pytest.mark.anyio
async def test_scraper_uses_http_response_and_deduplicates(test_session_factory) -> None:
    """A mocked website response becomes one source-linked document."""

    source = create_website()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == source.url
        return httpx.Response(
            200,
            text="<title>Notice</title><main>Port congestion</main>",
            headers={"content-type": "text/html"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first, created = await scrape_source(source, client)
        second, created_again = await scrape_source(source, client)
    assert first.title == "Notice"
    assert first.id == second.id
    assert (created, created_again) == (True, False)


@pytest.mark.anyio
async def test_scheduler_isolates_source_failures(test_session_factory) -> None:
    """One failed scheduled collection does not prevent another source run."""

    first = create_website()
    second = create_source(
        DataSourceCreate(
            name="Weather",
            type=SourceType.WEBSITE,
            url="https://example.com/weather",
            scrape_interval_minutes=1,
            scraper_type="HTML",
        )
    )
    now = datetime.now(timezone.utc) + timedelta(minutes=2)
    visited: list[str] = []

    async def collector(source) -> None:
        visited.append(source.id)
        if source.id == first.id:
            raise RuntimeError("timeout")

    assert await collect_due_sources(now=now, collector=collector) == 2
    assert visited == [first.id, second.id]
    assert get_source(first.id).last_status.value == "FAILED"
    assert get_source(second.id).last_status.value == "HEALTHY"


def test_upload_api_and_duplicate_response(test_session_factory) -> None:
    """The upload API creates a default upload source and reports duplicates."""

    class MemoryUpload:
        """Minimal async upload double independent of Starlette's thread pool."""

        filename = "notice.txt"
        content_type = "text/plain"

        async def read(self, _size: int) -> bytes:
            """Return deterministic in-memory content."""

            return b"Hai Phong warning"

    def upload():
        """Create one in-memory TXT upload."""

        return asyncio.run(
            document_api.upload_document(
                MemoryUpload(),  # type: ignore[arg-type]
                source_id=None,
            )
        )

    first = upload()
    second = upload()
    assert first.created is True
    assert second.created is False
    assert len(document_api.documents()) == 1


def test_disabled_source_is_not_due(test_session_factory) -> None:
    """Disabling a source removes its next scheduled run."""

    source = create_website()
    updated = update_source(source.id, DataSourceUpdate(enabled=False))
    assert updated is not None
    assert updated.next_run_at is None


def test_scheduler_has_one_coalesced_collection_job() -> None:
    """Application scheduling remains bounded to one due-source polling job."""

    scheduler = build_scheduler()
    job = scheduler.get_job("collect-due-sources")
    assert job is not None
    assert job.max_instances == 1
    assert job.coalesce is True


def test_discovery_parsers_and_canonicalization() -> None:
    """Feeds, sitemaps, and tracking variants produce stable article URLs."""

    feed = """<rss><channel><item><link>/news/closure?utm_source=x</link></item>
    <item><link>https://example.com/news/weather</link></item></channel></rss>"""
    sitemap = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>https://example.com/news/closure</loc></url></urlset>"""
    assert parse_feed(feed, "https://example.com/feed.xml") == [
        "https://example.com/news/closure",
        "https://example.com/news/weather",
    ]
    assert parse_sitemap(sitemap, "https://example.com/sitemap.xml") == [
        "https://example.com/news/closure"
    ]
    assert canonicalize_url(
        "/news/closure?utm_medium=email&id=7#details", "https://example.com"
    ) == "https://example.com/news/closure?id=7"


def test_keyword_pruning_keeps_navigation_and_rejects_noise() -> None:
    """Deterministic pruning retains news hubs and matching article links."""

    from app.domain.source import WebsiteDiscoveryConfig

    config = WebsiteDiscoveryConfig(
        enabled=True,
        keywords=["congestion", "typhoon"],
        allowed_paths=["/news"],
        excluded_paths=["/news/archive"],
    )
    assert should_enqueue_link(
        "https://example.com/news", "Latest news", "https://example.com", config
    )
    assert should_enqueue_link(
        "https://example.com/news/port-congestion",
        "Port congestion",
        "https://example.com",
        config,
    )
    assert not should_enqueue_link(
        "https://example.com/news/company-picnic",
        "Company picnic",
        "https://example.com",
        config,
    )
    assert not should_enqueue_link(
        "https://other.example/news/typhoon",
        "Typhoon",
        "https://example.com",
        config,
    )


def discovery_source(max_depth: int = 2, mode: str = "PAGE"):
    """Persist a website with bounded deterministic discovery enabled."""

    return create_source(
        DataSourceCreate(
            name=f"Discovery {max_depth} {mode}",
            type=SourceType.WEBSITE,
            url="https://example.com/",
            scrape_interval_minutes=30,
            scraper_type="HTML",
            scraper_config_json={
                "enabled": True,
                "mode": mode,
                "max_depth": max_depth,
                "max_pages": 20,
                "keywords": ["port", "congestion", "typhoon"],
                "allowed_paths": ["/news"],
                "excluded_paths": ["/news/archive"],
            },
        )
    )


@pytest.mark.anyio
async def test_bounded_bfs_finds_article_and_prunes_irrelevant_links(
    test_session_factory,
) -> None:
    """A depth-two crawl traverses a news hub but ignores unrelated pages."""

    source = discovery_source()
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        requested.append(path)
        pages = {
            "/robots.txt": (200, "User-agent: *\nAllow: /", "text/plain"),
            "/": (
                200,
                '<a href="/news">News</a><a href="/careers">Careers</a>',
                "text/html",
            ),
            "/news": (
                200,
                '<a href="/news/port-congestion">Port congestion</a>'
                '<a href="/news/company-picnic">Company picnic</a>'
                '<a href="/news/archive/2020">News archive</a>',
                "text/html",
            ),
            "/news/port-congestion": (
                200,
                "<title>Port congestion</title><article>Hai Phong port congestion.</article>",
                "text/html",
            ),
        }
        status, body, media_type = pages.get(path, (404, "missing", "text/plain"))
        return httpx.Response(
            status,
            text=body,
            headers={"content-type": media_type},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await discover_and_scrape_source(source, client)
    assert result.created_documents == 1
    assert result.documents[0].source_url == "https://example.com/news/port-congestion"
    assert "/news" in requested
    assert "/news/port-congestion" in requested
    assert "/careers" not in requested
    assert "/news/company-picnic" not in requested
    assert "/news/archive/2020" not in requested


@pytest.mark.anyio
async def test_depth_limit_stops_before_article(test_session_factory) -> None:
    """Maximum depth prevents deeper URLs from being requested or ingested."""

    source = discovery_source(max_depth=1)
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        body = (
            '<a href="/news">News</a>'
            if request.url.path == "/"
            else '<a href="/news/port-congestion">Port congestion</a>'
        )
        return httpx.Response(
            200,
            text="User-agent: *\nAllow: /" if request.url.path == "/robots.txt" else body,
            headers={"content-type": "text/plain" if request.url.path == "/robots.txt" else "text/html"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await discover_and_scrape_source(source, client)
    assert result.created_documents == 0
    assert "/news/port-congestion" not in requested


@pytest.mark.anyio
async def test_rss_seeds_articles_without_consuming_html_depth(
    test_session_factory,
) -> None:
    """An explicit RSS feed directly seeds terminal article documents."""

    source = create_source(
        DataSourceCreate(
            name="RSS notices",
            type=SourceType.WEBSITE,
            url="https://example.com/",
            scrape_interval_minutes=30,
            scraper_type="HTML",
            scraper_config_json={
                "enabled": True,
                "mode": "RSS",
                "max_depth": 0,
                "max_pages": 10,
                "keywords": ["typhoon"],
                "feed_url": "https://example.com/feed.xml",
            },
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            body, media_type = "User-agent: *\nAllow: /", "text/plain"
        elif request.url.path == "/feed.xml":
            body = "<rss><channel><item><link>/news/typhoon</link></item></channel></rss>"
            media_type = "application/rss+xml"
        else:
            body, media_type = (
                "<title>Typhoon warning</title><article>Port closure expected.</article>",
                "text/html",
            )
        return httpx.Response(
            200,
            text=body,
            headers={"content-type": media_type},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await discover_and_scrape_source(source, client)
    assert result.created_documents == 1
    assert result.documents[0].title == "Typhoon warning"


@pytest.mark.anyio
async def test_robots_rules_are_respected(test_session_factory) -> None:
    """Disallowed article paths are never fetched."""

    source = discovery_source()
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            body, media_type = "User-agent: *\nDisallow: /news/private", "text/plain"
        elif request.url.path == "/":
            body, media_type = '<a href="/news/private/port">Port alert</a>', "text/html"
        else:
            body, media_type = "<article>Port congestion</article>", "text/html"
        return httpx.Response(
            200,
            text=body,
            headers={"content-type": media_type},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await discover_and_scrape_source(source, client)
    assert result.created_documents == 0
    assert "/news/private/port" not in requested


@pytest.mark.anyio
async def test_sitemap_index_seeds_terminal_articles(test_session_factory) -> None:
    """Nested sitemap indexes resolve article URLs without HTML traversal depth."""

    source = create_source(
        DataSourceCreate(
            name="Sitemap notices",
            type=SourceType.WEBSITE,
            url="https://example.com/",
            scrape_interval_minutes=30,
            scraper_type="HTML",
            scraper_config_json={
                "enabled": True,
                "mode": "SITEMAP",
                "max_depth": 0,
                "max_pages": 10,
                "keywords": ["closure"],
                "sitemap_url": "https://example.com/sitemap-index.xml",
            },
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        responses = {
            "/robots.txt": (
                "User-agent: *\nAllow: /",
                "text/plain",
            ),
            "/sitemap-index.xml": (
                '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                "<sitemap><loc>https://example.com/post-sitemap1.xml</loc></sitemap>"
                "</sitemapindex>",
                "application/xml",
            ),
            "/post-sitemap1.xml": (
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                "<url><loc>https://example.com/news/closure</loc></url>"
                "</urlset>",
                "application/xml",
            ),
            "/news/closure": (
                "<title>Terminal closure</title><article>Port closure.</article>",
                "text/html",
            ),
        }
        body, media_type = responses[request.url.path]
        return httpx.Response(
            200,
            text=body,
            headers={"content-type": media_type},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await discover_and_scrape_source(source, client)
    assert result.created_documents == 1
    assert result.documents[0].source_url == "https://example.com/news/closure"
