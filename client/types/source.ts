import type { Evidence } from "@/types/evidence";

/** Ingestion mechanisms a user can configure in the platform. */
export type SourceType = "WEBSITE" | "UPLOAD";

/** Health summary derived from a source's most recent collection run. */
export type SourceRunStatus = "NEVER" | "HEALTHY" | "FAILED";

/** Bounded crawl and feed-discovery settings for a website source. */
export interface WebsiteDiscoveryConfig {
    /** Whether linked-page, feed, or sitemap discovery extends beyond the seed URL. */
    enabled: boolean;
    /** Discovery strategy; AUTO selects an appropriate strategy from available metadata. */
    mode: "PAGE" | "RSS" | "SITEMAP" | "AUTO";
    /** Maximum navigation distance from the configured seed URL. */
    max_depth: number;
    /** Hard cap on pages fetched during one collection run. */
    max_pages: number;
    /** Case-insensitive terms used to retain relevant discovered pages. */
    keywords: string[];
    /** URL path prefixes eligible for collection; empty means any same-site path. */
    allowed_paths: string[];
    /** URL path prefixes excluded from collection. */
    excluded_paths: string[];
    /** Explicit feed URL used by RSS discovery, when configured. */
    feed_url: string | null;
    /** Explicit sitemap URL used by sitemap discovery, when configured. */
    sitemap_url: string | null;
}

/** Persisted user-managed ingestion source returned by the source API. */
export interface DataSource {
    id: string;
    name: string;
    type: SourceType;
    description: string;
    url: string | null;
    enabled: boolean;
    /** Interval between scheduled website collections; absent for upload sources. */
    scrape_interval_minutes: number | null;
    /** Collector implementation selected for website sources. */
    scraper_type: string | null;
    /** Collector-specific configuration; currently the website discovery settings. */
    scraper_config_json: Partial<WebsiteDiscoveryConfig> | null;
    last_run_at: string | null;
    next_run_at: string | null;
    last_status: SourceRunStatus;
    last_error: string | null;
    created_at: string;
    updated_at: string;
}

/** One unexpected evidence-processing failure safe to display to users. */
export interface SourceProcessingError {
    evidence_id: string;
    message: string;
}

/** Aggregate processing outcomes for newly collected, non-duplicate evidence. */
export interface SourceProcessingSummary {
    attempted: number;
    ready_for_review: number;
    filtered_out: number;
    needs_resolution: number;
    mapping_failed: number;
    failed: number;
    /** Items postponed after shared provider capacity was exhausted. */
    deferred: number;
    errors: SourceProcessingError[];
}

/** Synchronous collection and signal-processing response. */
export interface SourceCollectionResult {
    source_id: string;
    evidence: Evidence[];
    discovered_urls: number;
    fetched_pages: number;
    skipped_urls: number;
    created_evidence: number;
    duplicate_evidence: number;
    errors: string[];
    processing: SourceProcessingSummary;
}
