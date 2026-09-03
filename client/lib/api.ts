import type { DataSource, SchedulingStatus } from "@/types/source";
import type { Evidence } from "@/types/evidence";
import type { Signal } from "@/types/signal";
import type { PlanningCycle } from "@/types/planning";
import type { AgentPrompt } from "@/types/prompt";

/** Health and version information for the authoritative client integration. */
export interface ClientConnection {
    status: "ok" | "degraded";
    client_id: string | null;
    context_version: string | null;
    schema_version: string | null;
    state_version: string | null;
    capability_version: string | null;
    last_successful_response_at: string | null;
    error_code: string | null;
}

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
    const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
    const response = await fetch(`${backendUrl}${path}`, {
        ...init,
        cache: "no-store",
    });

    if (!response.ok) {
        throw new Error(`FastAPI returned ${response.status} for ${path}`);
    }

    return (await response.json()) as T;
}

export async function getClientConnection(): Promise<ClientConnection> {
    return fetchApi<ClientConnection>("/health/client");
}

export async function getSources(): Promise<DataSource[]> {
    return fetchApi<DataSource[]>("/api/sources");
}

export async function getSchedulingStatus(): Promise<SchedulingStatus> {
    return fetchApi<SchedulingStatus>("/api/sources/scheduling/status");
}

export async function getEvidence(archived = false, limit = 50, offset = 0,
                                  includeDuplicates = false): Promise<Evidence[]> {
    return fetchApi<Evidence[]>(`/api/evidence?archived=${archived}&include_duplicates=${includeDuplicates}&limit=${limit}&offset=${offset}`);
}

export async function getEvidenceItem(id: string): Promise<Evidence> {
    return fetchApi<Evidence>(`/api/evidence/${encodeURIComponent(id)}`);
}

export async function getSignals(reviewStatus?: string, limit = 50, offset = 0): Promise<Signal[]> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (reviewStatus) params.set("review_status", reviewStatus);
    return fetchApi<Signal[]>(`/api/signals?${params}`);
}

export async function getPlanningCycles(): Promise<PlanningCycle[]> {
    return fetchApi<PlanningCycle[]>("/api/planning/cycles");
}

export async function getAgentPrompts(): Promise<AgentPrompt[]> {
    return fetchApi<AgentPrompt[]>("/api/settings/prompts");
}
