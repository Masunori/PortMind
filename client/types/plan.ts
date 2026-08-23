export type PlanActionType =
    | "REROUTE_SHIPMENT"
    | "EXPEDITE_SHIPMENT"
    | "USE_ALTERNATIVE_INVENTORY"
    | "WAIT";

export type PlanAction = {
    type: PlanActionType;
    shipment_id?: string | null;
    new_route?: string[] | null;
    alternative_inventory_node_id?: string | null;
    transit_time_multiplier: number;
    cost_multiplier: number;
};

export type Plan = {
    id: string;
    name: string;
    actions: PlanAction[];
    status: "GENERATED" | "RECOMMENDED" | "APPROVED" | "REJECTED";
};

export type PlanScenarioResult = {
    plan_id: string;
    plan_name: string;
    scenario_id: string;
    scenario_name: string;
    probability: number;
    total_cost: number;
    average_lead_time_hours: number;
    delay_hours: number;
    late_shipments: number;
};

export type PlanComparisonActionState =
    | { results: PlanScenarioResult[]; error: null }
    | { results: null; error: string | null };

export type RankingWeights = {
    cost: number;
    delay: number;
    risk: number;
};

export type RankedPlan = {
    rank: number;
    plan_id: string;
    plan_name: string;
    expected_cost: number;
    expected_delay: number;
    worst_case_cost: number;
    score: number;
};

export type PlanRankingResult = {
    recommended_plan: string;
    expected_cost: number;
    expected_delay: number;
    worst_case_cost: number;
    weights: RankingWeights;
    plans: RankedPlan[];
};

export type PlanRankingActionState =
    | { result: PlanRankingResult; error: null }
    | { result: null; error: string | null };
