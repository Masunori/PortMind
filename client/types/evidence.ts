/** Origin or storage form of a canonical evidence item. */
export type EvidenceKind =
    | "UPLOAD"
    | "WEBSITE"
    | "RSS"
    | "API"
    | "STRUCTURED"
    | "MANUAL"
    | "LARGE_CONTENT_REFERENCE";

/** Canonical evidence envelope returned by the evidence management API. */
export interface Evidence {
    id: string;
    source_id: string;
    collection_run_id: string | null;
    kind: EvidenceKind;
    title: string;
    media_type: string;
    content: string | null;
    /** Parsed machine-readable payload when the item is not plain text. */
    structured_content: Record<string, unknown> | unknown[] | null;
    /** External object reference used when raw content is stored elsewhere. */
    content_reference: string | null;
    /** SHA-256 digest used for content-level deduplication. */
    content_hash: string;
    /** Canonical item containing identical content, if this is a duplicate. */
    duplicate_of_id: string | null;
    source_url: string | null;
    published_at: string | null;
    collected_at: string;
    processed_at: string | null;
    processing_status: "PENDING" | "COMPLETE" | "PARTIAL" | "FAILED";
    /** Parser warnings retained for review rather than treated as hard failures. */
    parser_warnings: string[];
    /** Source- or parser-specific quality measurements and annotations. */
    quality_metadata: Record<string, unknown>;
    /** Policy controlling expiry, raw-content removal, and permanent deletion. */
    retention_class: "TRANSIENT" | "STANDARD" | "AUDIT" | "LEGAL_HOLD";
    expires_at: string | null;
    archived_at: string | null;
}

export interface DeletionImpact {
    evidence_id: string;
    can_remove_raw_content: boolean;
    can_delete_permanently: boolean;
    protected_by: Array<
        "signal_versions" | "duplicate_evidence" | "legal_hold" | string
    >;
    raw_content_present: boolean;
}

export interface DuplicateDeletionCandidate {
    evidence_id: string;
    can_delete: boolean;
    protected_by: string[];
}

export interface DuplicateDeletionPreview {
    canonical_evidence_id: string;
    candidates: DuplicateDeletionCandidate[];
}

export interface DuplicateDeletionResult {
    canonical_evidence_id: string;
    deleted_ids: string[];
    skipped: DuplicateDeletionCandidate[];
    canonical_deleted: boolean;
}

export interface EvidenceProcessingAttempt {
    signal_id: string;
    signal_version_id: string;
    signal_type: string;
    retry_of_signal_id: string | null;
    review_status: string;
    processing_state: string;
    created_at: string;
}

export interface EvidenceProcessingEligibility {
    evidence_id: string;
    can_process: boolean;
    retry_of_signal_id: string | null;
    blocked_by: string[];
    attempts: EvidenceProcessingAttempt[];
}
