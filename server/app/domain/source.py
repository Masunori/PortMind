"""User-facing ingestion source contracts."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.integrations.contracts import Evidence


class SourceType(str, Enum):
    """Identify website and uploaded-document source groups."""

    WEBSITE = "WEBSITE"
    UPLOAD = "UPLOAD"


class SourceRunStatus(str, Enum):
    """Summarize the latest collection attempt for a source."""

    NEVER = "NEVER"
    HEALTHY = "HEALTHY"
    FAILED = "FAILED"


class DiscoveryMode(str, Enum):
    """Select how a website source discovers article URLs."""

    PAGE = "PAGE"
    RSS = "RSS"
    SITEMAP = "SITEMAP"
    AUTO = "AUTO"


class WebsiteDiscoveryConfig(BaseModel):
    """Bound deterministic discovery for one website source."""

    enabled: bool = False
    mode: DiscoveryMode = DiscoveryMode.AUTO
    max_depth: int = Field(default=2, ge=0, le=5)
    max_pages: int = Field(default=50, ge=1, le=500)
    keywords: list[str] = Field(default_factory=list, max_length=50)
    allowed_paths: list[str] = Field(default_factory=list, max_length=25)
    excluded_paths: list[str] = Field(default_factory=list, max_length=25)
    feed_url: str | None = None
    sitemap_url: str | None = None

    @model_validator(mode="after")
    def validate_urls_and_terms(self) -> "WebsiteDiscoveryConfig":
        """Validate optional seed URLs and normalize user-entered filters."""

        for value in (self.feed_url, self.sitemap_url):
            if value is not None and not value.startswith(("http://", "https://")):
                raise ValueError("Discovery URLs must use HTTP(S)")
        self.keywords = sorted(
            {item.strip().casefold() for item in self.keywords if item.strip()}
        )
        self.allowed_paths = [item.strip() for item in self.allowed_paths if item.strip()]
        self.excluded_paths = [item.strip() for item in self.excluded_paths if item.strip()]
        return self


class DataSourceCreate(BaseModel):
    """Fields accepted when users create a source."""

    name: str = Field(min_length=1, max_length=200)
    type: SourceType
    description: str = ""
    url: str | None = None
    enabled: bool = True
    schedule_enabled: bool = False
    scrape_interval_minutes: int | None = Field(default=None, ge=1)
    scraper_type: str | None = None
    scraper_config_json: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_type_configuration(self) -> "DataSourceCreate":
        """Require website collection fields and clear upload scraping fields."""

        if self.type is SourceType.WEBSITE:
            if not self.url or not self.url.startswith(("http://", "https://")):
                raise ValueError("Website sources require an HTTP(S) URL")
            if self.scrape_interval_minutes is None:
                raise ValueError("Website sources require a scrape interval")
            if not self.scraper_type:
                raise ValueError("Website sources require a scraper type")
            if self.scraper_config_json is not None:
                self.scraper_config_json = WebsiteDiscoveryConfig.model_validate(
                    self.scraper_config_json
                ).model_dump(mode="json")
        elif any(
            value is not None
            for value in (
                self.url,
                self.scrape_interval_minutes,
                self.scraper_type,
                self.scraper_config_json,
            )
        ):
            raise ValueError("Upload sources cannot contain scraper configuration")
        elif self.schedule_enabled:
            raise ValueError("Upload sources cannot enable scheduling")
        return self


class DataSourceUpdate(BaseModel):
    """Partial source update accepted by the management API."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    url: str | None = None
    enabled: bool | None = None
    schedule_enabled: bool | None = None
    scrape_interval_minutes: int | None = Field(default=None, ge=1)
    scraper_type: str | None = None
    scraper_config_json: dict[str, object] | None = None


class DataSource(BaseModel):
    """Return a persisted user-facing ingestion source."""

    id: str
    name: str
    type: SourceType
    description: str
    url: str | None
    enabled: bool
    schedule_enabled: bool
    scrape_interval_minutes: int | None
    scraper_type: str | None
    scraper_config_json: dict[str, object] | None
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_status: SourceRunStatus
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def discovery(self) -> WebsiteDiscoveryConfig:
        """Return validated discovery configuration with safe legacy defaults."""

        return WebsiteDiscoveryConfig.model_validate(self.scraper_config_json or {})


class SourceProcessingError(BaseModel):
    """Describe an unexpected failure while processing one evidence item."""

    evidence_id: str
    message: str


class SourceProcessingSummary(BaseModel):
    """Aggregate terminal processing outcomes for newly collected evidence."""

    attempted: int = 0
    ready_for_review: int = 0
    filtered_out: int = 0
    needs_resolution: int = 0
    mapping_failed: int = 0
    failed: int = 0
    deferred: int = 0
    errors: list[SourceProcessingError] = Field(default_factory=list)


class SourceCollectionResult(BaseModel):
    """Summarize one bounded website collection run."""

    source_id: str
    evidence: list[Evidence]
    discovered_urls: int
    fetched_pages: int
    skipped_urls: int
    created_evidence: int
    duplicate_evidence: int
    errors: list[str] = Field(default_factory=list)
    processing: SourceProcessingSummary = Field(default_factory=SourceProcessingSummary)
