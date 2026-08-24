import type { ExposureAnalysis } from "@/types/disruption";

export interface DisruptionCandidate {
    id: string;
    document_id: string;
    event_id: string | null;
    disruption_type: string;
    affected_locations: string[];
    affected_node_ids: string[];
    affected_edge_ids: string[];
    start_time: number;
    end_time: number;
    probability: number;
    severity: number;
    effects: Record<string, unknown>;
    summary: string;
    extraction_confidence: number;
    validation_status: "EXTRACTED" | "VALIDATED" | "INVALID";
    validation_errors: string[];
    review_status: "PENDING" | "ACCEPTED" | "REJECTED";
    confirmed_disruption_id: string | null;
    run_id: string | null;
    created_at: string;
    updated_at: string;
}

export interface CandidateInboxItem {
    candidate: DisruptionCandidate;
    exposure: ExposureAnalysis | null;
}
