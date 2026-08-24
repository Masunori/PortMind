"""Bounded same-site discovery for feeds, sitemaps, and HTML navigation."""

from collections import deque
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ElementTree

from bs4 import BeautifulSoup
import httpx

from app.domain.document import DocumentCreate
from app.domain.source import (
    DataSource,
    DiscoveryMode,
    SourceCollectionResult,
    SourceType,
    WebsiteDiscoveryConfig,
)
from app.ingestion.extractors import extract_html
from app.services.document_service import store_document

NAVIGATION_TERMS = {
    "article",
    "alert",
    "insight",
    "media",
    "news",
    "notice",
    "press",
    "release",
    "update",
}
TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


@dataclass(frozen=True)
class QueueEntry:
    """Represent one canonical URL and its HTML traversal depth."""

    url: str
    depth: int
    terminal: bool = False


def canonicalize_url(url: str, base_url: str) -> str | None:
    """Resolve and normalize a crawl URL while rejecting unsupported schemes."""

    resolved = urljoin(base_url, url)
    parsed = urlsplit(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in TRACKING_PARAMETERS
    ]
    path = parsed.path or "/"
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            path,
            urlencode(filtered_query),
            "",
        )
    )


def _same_site(candidate: str, root: str) -> bool:
    """Restrict discovery to the configured host and port."""

    return urlsplit(candidate).netloc.casefold() == urlsplit(root).netloc.casefold()


def _path_allowed(url: str, config: WebsiteDiscoveryConfig) -> bool:
    """Apply configured path prefixes before a URL enters the queue."""

    path = urlsplit(url).path.casefold()
    if config.excluded_paths and any(
        path.startswith(item.casefold()) for item in config.excluded_paths
    ):
        return False
    return not config.allowed_paths or any(
        path.startswith(item.casefold()) for item in config.allowed_paths
    )


def _contains_keyword(value: str, config: WebsiteDiscoveryConfig) -> bool:
    """Return whether normalized text contains a configured keyword."""

    normalized = " ".join(value.casefold().split())
    return not config.keywords or any(term in normalized for term in config.keywords)


def should_enqueue_link(
    url: str,
    anchor_text: str,
    root_url: str,
    config: WebsiteDiscoveryConfig,
) -> bool:
    """Prune off-site, excluded, and semantically irrelevant navigation URLs."""

    if not _same_site(url, root_url) or not _path_allowed(url, config):
        return False
    if not config.keywords:
        return True
    path = urlsplit(url).path.casefold()
    value = f"{path} {anchor_text}".casefold()
    if _contains_keyword(value, config):
        return True
    final_segment = path.rstrip("/").rsplit("/", 1)[-1]
    anchor_tokens = set(anchor_text.casefold().split())
    return final_segment in NAVIGATION_TERMS or bool(anchor_tokens & NAVIGATION_TERMS)


def parse_feed(xml: str, base_url: str) -> list[str]:
    """Extract canonical article links from RSS or Atom XML."""

    root = ElementTree.fromstring(xml)
    urls: list[str] = []
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1].casefold()
        candidate: str | None = None
        if name == "link":
            candidate = element.attrib.get("href") or (element.text or "").strip()
        if candidate and (normalized := canonicalize_url(candidate, base_url)):
            urls.append(normalized)
    return list(dict.fromkeys(urls))


def parse_sitemap(xml: str, base_url: str) -> list[str]:
    """Extract URLs from either a sitemap or sitemap index."""

    root = ElementTree.fromstring(xml)
    urls = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].casefold() != "loc" or not element.text:
            continue
        normalized = canonicalize_url(element.text.strip(), base_url)
        if normalized:
            urls.append(normalized)
    return list(dict.fromkeys(urls))


def _html_links(html: str, base_url: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Extract ordinary navigation links and advertised RSS/Atom feeds."""

    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str]] = []
    feeds: list[str] = []
    for element in soup.find_all("a", href=True):
        normalized = canonicalize_url(str(element["href"]), base_url)
        if normalized:
            links.append((normalized, element.get_text(" ", strip=True)))
    for element in soup.find_all("link", href=True):
        media_type = str(element.get("type", "")).casefold()
        rel = {str(item).casefold() for item in element.get("rel", [])}
        if "alternate" in rel and media_type in {
            "application/atom+xml",
            "application/rss+xml",
        }:
            normalized = canonicalize_url(str(element["href"]), base_url)
            if normalized:
                feeds.append(normalized)
    return links, list(dict.fromkeys(feeds))


def _looks_like_article(html: str) -> bool:
    """Identify terminal article markup without relying on a model call."""

    soup = BeautifulSoup(html, "html.parser")
    if soup.find("article") is not None:
        return True
    marker = soup.find("meta", attrs={"property": "og:type"})
    return bool(marker and str(marker.get("content", "")).casefold() == "article")


async def _robots_parser(
    root_url: str,
    client: httpx.AsyncClient,
) -> RobotFileParser:
    """Load same-site robots rules, defaulting to permissive on fetch failure."""

    parsed = urlsplit(root_url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    parser = RobotFileParser(robots_url)
    try:
        response = await client.get(robots_url)
        if response.status_code < 400:
            parser.parse(response.text.splitlines())
        else:
            parser.parse([])
    except httpx.HTTPError:
        parser.parse([])
    return parser


async def discover_and_scrape_source(
    source: DataSource,
    client: httpx.AsyncClient | None = None,
) -> SourceCollectionResult:
    """Discover and ingest relevant articles using a bounded breadth-first crawl."""

    if source.type is not SourceType.WEBSITE or source.url is None:
        raise ValueError("Only website sources can be discovered")
    config = source.discovery
    if not config.enabled:
        from app.ingestion.scraper import scrape_source

        document, created = await scrape_source(source, client)
        return SourceCollectionResult(
            source_id=source.id,
            documents=[document],
            discovered_urls=1,
            fetched_pages=1,
            skipped_urls=0,
            created_documents=int(created),
            duplicate_documents=int(not created),
        )

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=20, follow_redirects=True)
    queue: deque[QueueEntry] = deque()
    seen: set[str] = set()
    queued: set[str] = set()
    documents = []
    created_count = 0
    duplicate_count = 0
    skipped = 0
    fetched = 0
    errors: list[str] = []

    def enqueue(
        url: str,
        depth: int,
        terminal: bool = False,
        seed: bool = False,
    ) -> None:
        """Add an allowed unique URL without exceeding discovery semantics."""

        nonlocal skipped
        normalized = canonicalize_url(url, source.url or url)
        if (
            normalized is None
            or normalized in seen
            or normalized in queued
            or not _same_site(normalized, source.url or normalized)
            or (not seed and not _path_allowed(normalized, config))
        ):
            skipped += 1
            return
        queued.add(normalized)
        queue.append(QueueEntry(normalized, depth, terminal))

    if config.mode in {DiscoveryMode.PAGE, DiscoveryMode.AUTO}:
        enqueue(source.url, 0, seed=True)
    if config.mode is DiscoveryMode.RSS:
        enqueue(config.feed_url or source.url, 0, True, seed=True)
    elif config.feed_url:
        enqueue(config.feed_url, 0, True, seed=True)
    if config.mode is DiscoveryMode.SITEMAP:
        enqueue(config.sitemap_url or source.url, 0, True, seed=True)
    elif config.sitemap_url:
        enqueue(config.sitemap_url, 0, True, seed=True)
    if config.mode is DiscoveryMode.AUTO and not config.sitemap_url:
        enqueue(urljoin(source.url, "/sitemap.xml"), 0, True, seed=True)

    try:
        robots = await _robots_parser(source.url, active_client)
        while queue and fetched < config.max_pages:
            entry = queue.popleft()
            queued.discard(entry.url)
            if entry.url in seen:
                continue
            seen.add(entry.url)
            if not robots.can_fetch("PSA-ESG-Discovery/1.0", entry.url):
                skipped += 1
                continue
            try:
                response = await active_client.get(entry.url)
                fetched += 1
                response.raise_for_status()
            except (httpx.HTTPError, ValueError) as error:
                errors.append(f"{entry.url}: {error}")
                continue
            media_type = response.headers.get("content-type", "").split(";", 1)[0]
            if media_type in {"application/rss+xml", "application/atom+xml"}:
                try:
                    for url in parse_feed(response.text, entry.url):
                        enqueue(url, 0, True)
                except ElementTree.ParseError as error:
                    errors.append(f"{entry.url}: invalid feed ({error})")
                continue
            if media_type in {"application/xml", "text/xml"} or entry.url.endswith(".xml"):
                try:
                    xml_root = ElementTree.fromstring(response.text)
                    is_sitemap_index = (
                        xml_root.tag.rsplit("}", 1)[-1].casefold() == "sitemapindex"
                    )
                    for url in parse_sitemap(response.text, entry.url):
                        enqueue(
                            url,
                            0,
                            terminal=not is_sitemap_index,
                            seed=is_sitemap_index,
                        )
                except ElementTree.ParseError as error:
                    errors.append(f"{entry.url}: invalid sitemap ({error})")
                continue
            if media_type and media_type != "text/html":
                skipped += 1
                continue
            title, content = extract_html(response.text)
            content_relevant = _contains_keyword(
                f"{entry.url} {title} {content[:4000]}", config
            )
            article = entry.terminal or (
                entry.depth > 0 and _looks_like_article(response.text)
            )
            if article and content_relevant and content.strip():
                document, created = store_document(
                    DocumentCreate(
                        source_id=source.id,
                        title=title,
                        source_url=str(response.url),
                        media_type=media_type or "text/html",
                        content=content,
                    )
                )
                documents.append(document)
                created_count += int(created)
                duplicate_count += int(not created)
            if article or entry.depth >= config.max_depth:
                continue
            links, feeds = _html_links(response.text, entry.url)
            if config.mode is DiscoveryMode.AUTO:
                for feed in feeds:
                    enqueue(feed, 0, True, seed=True)
            for url, anchor in links:
                if should_enqueue_link(url, anchor, source.url, config):
                    enqueue(url, entry.depth + 1)
                else:
                    skipped += 1
    finally:
        if owns_client:
            await active_client.aclose()

    return SourceCollectionResult(
        source_id=source.id,
        documents=documents,
        discovered_urls=len(seen) + len(queue),
        fetched_pages=fetched,
        skipped_urls=skipped,
        created_documents=created_count,
        duplicate_documents=duplicate_count,
        errors=errors,
    )
