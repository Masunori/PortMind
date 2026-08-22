import type { Disruption, ExposureAnalysis } from "@/types/disruption";
import type { Network, NetworkResponse, Shipment } from "@/types/network";
import type { Scenario, ScenarioSimulationResult } from "@/types/scenario";
import type {
    Plan,
    PlanRankingResult,
    PlanScenarioResult,
    RankingWeights,
} from "@/types/plan";
import type { SimulationResult } from "@/types/simulation";

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

export async function getSupplyChainData(): Promise<NetworkResponse> {
    const [network, shipments, disruptions, scenarios, plans] = await Promise.all([
        fetchApi<Network>("/api/network"),
        fetchApi<Shipment[]>("/api/shipments"),
        getDisruptions(),
        getScenarios(),
        getPlans(),
    ]);
    const exposures = await Promise.all(
        disruptions
            .filter((disruption) => disruption.enabled)
            .map((disruption) => getDisruptionExposure(disruption.id)),
    );

    return { network, shipments, disruptions, exposures, scenarios, plans };
}

export async function requestBaselineSimulation(): Promise<SimulationResult> {
    return fetchApi<SimulationResult>("/api/simulations", { method: "POST" });
}

export async function getDisruptions(): Promise<Disruption[]> {
    return fetchApi<Disruption[]>("/api/disruptions");
}

export async function getScenarios(): Promise<Scenario[]> {
    return fetchApi<Scenario[]>("/api/scenarios");
}

export async function requestAllScenarioSimulations(): Promise<
    ScenarioSimulationResult[]
> {
    return fetchApi<ScenarioSimulationResult[]>("/api/scenarios/simulate-all", {
        method: "POST",
    });
}

export async function getPlans(): Promise<Plan[]> {
    return fetchApi<Plan[]>("/api/plans");
}

export async function requestPlanComparison(): Promise<PlanScenarioResult[]> {
    return fetchApi<PlanScenarioResult[]>("/api/plans/compare", {
        method: "POST",
    });
}

export async function requestPlanRanking(
    weights: RankingWeights,
): Promise<PlanRankingResult> {
    return fetchApi<PlanRankingResult>("/api/plans/rank", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(weights),
    });
}

export async function getDisruptionExposure(
    disruptionId: string,
): Promise<ExposureAnalysis> {
    return fetchApi<ExposureAnalysis>(
        `/api/disruptions/${disruptionId}/exposure`,
    );
}

export async function injectPortCongestion(): Promise<Disruption> {
    const disruption: Disruption = {
        id: "hai-phong-port-congestion",
        type: "PORT_CONGESTION",
        enabled: true,
        affected_node_ids: ["hai-phong-port"],
        affected_edge_ids: [],
        start_time: 0,
        end_time: 48,
        effects: {
            handling_time_multiplier: 2,
        },
    };

    return fetchApi<Disruption>("/api/disruptions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(disruption),
    });
}

export async function setDisruptionEnabled(
    disruptionId: string,
    enabled: boolean,
): Promise<Disruption> {
    return fetchApi<Disruption>(`/api/disruptions/${disruptionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
    });
}
