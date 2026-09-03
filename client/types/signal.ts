export interface GroundedEntity {
    mention: string;
    is_target: boolean;
    status: string;
    entity_id: string | null;
    entity_type: string | null;
    method: string;
    confidence: number;
}

export interface Signal {
    id: string;
    signal_id: string;
    retry_of_signal_id: string | null;
    version: number;
    classification: string;
    signal_type: string;
    temporal_window: { starts_at: string; ends_at: string | null };
    occurrence_probability: number;
    severity: number;
    extraction_confidence: number;
    grounding_confidence: number | null;
    mapping_confidence: number | null;
    evidence_ids: string[];
    entities: GroundedEntity[];
    context_version: string;
    lifecycle_status: string;
    review_status: string;
    processing_state: string;
    mapping_outcome: string | null;
    mapping_errors: string[];
    mapping_proposal: Record<string, unknown> | null;
    local_validation: Record<string, unknown> | null;
    client_validation: Record<string, unknown> | null;
    normalized_disruption: Record<string, unknown> | null;
    catalog_version: string | null;
    schema_hash: string | null;
    provider_metadata: Record<string, unknown>;
}
