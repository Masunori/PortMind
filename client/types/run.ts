import type { Plan, PlanScenarioResult, PlanRankingResult } from "@/types/plan";
import type { Scenario } from "@/types/scenario";

export type RunStatus = "GENERATED" | "RUNNING" | "COMPLETED" | "FAILED";

export type RunEventType =
    | "RUN_STARTED"
    | "SIGNAL_INTERPRETED"
    | "ENTITIES_GROUNDED"
    | "EXPOSURE_ANALYZED"
    | "SCENARIOS_GENERATED"
    | "PLANS_GENERATED"
    | "SIMULATION_STARTED"
    | "SIMULATION_COMPLETED"
    | "RANKING_COMPLETED"
    | "RUN_COMPLETED"
    | "RUN_FAILED";

export type RunEvent = {
    sequence: number;
    type: RunEventType;
    payload: Record<string, unknown>;
    created_at: string;
};

export type RunResponse = {
    run_id: string;
    status: RunStatus;
    signal: string;
    scenarios: Scenario[];
    plans: Plan[];
    results: PlanScenarioResult[];
    recommendation: PlanRankingResult | null;
    error: string | null;
};
