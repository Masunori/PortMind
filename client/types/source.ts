export type SourceType = "WEBSITE" | "UPLOAD";
export type SourceRunStatus = "NEVER" | "HEALTHY" | "FAILED";

export interface WebsiteDiscoveryConfig {
    enabled: boolean;
    mode: "PAGE" | "RSS" | "SITEMAP" | "AUTO";
    max_depth: number;
    max_pages: number;
    keywords: string[];
    allowed_paths: string[];
    excluded_paths: string[];
    feed_url: string | null;
    sitemap_url: string | null;
}

export interface DataSource {
    id: string;
    name: string;
    type: SourceType;
    description: string;
    url: string | null;
    enabled: boolean;
    scrape_interval_minutes: number | null;
    scraper_type: string | null;
    scraper_config_json: Partial<WebsiteDiscoveryConfig> | null;
    last_run_at: string | null;
    next_run_at: string | null;
    last_status: SourceRunStatus;
    last_error: string | null;
    created_at: string;
    updated_at: string;
}

export interface RawDocument {
    id: string;
    source_id: string;
    title: string;
    source_url: string | null;
    media_type: string;
    content: string;
    content_hash: string;
    status: "NEW" | "PROCESSED" | "FAILED";
    error: string | null;
    collected_at: string;
    created_at: string;
}

export interface DocumentAssessment {
    document_id: string;
    decision: "RELEVANT" | "IRRELEVANT" | "NEEDS_REVIEW";
    effective_decision: "RELEVANT" | "IRRELEVANT" | "NEEDS_REVIEW";
    relevance_probability: number;
    rationale: string;
    matched_entities: string[];
    human_override: "RELEVANT" | "IRRELEVANT" | "NEEDS_REVIEW" | null;
    assessed_at: string;
    updated_at: string;
}

export interface DocumentReviewItem {
    document: RawDocument;
    assessment: DocumentAssessment | null;
}
