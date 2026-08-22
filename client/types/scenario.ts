import type { Disruption } from "@/types/disruption";

export type Scenario = {
    id: string;
    name: string;
    probability: number;
    disruptions: Disruption[];
};

export type ScenarioSimulationResult = {
    scenario_id: string;
    name: string;
    probability: number;
    total_cost: number;
    average_lead_time_hours: number;
    delay_hours: number;
    late_shipments: number;
};

export type ScenarioActionState =
    | { results: ScenarioSimulationResult[]; error: null }
    | { results: null; error: string | null };
