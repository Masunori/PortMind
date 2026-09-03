export type PlanningLifecycle =
    | "PROPOSED" | "VALIDATED" | "SUBMITTED" | "RUNNING" | "EVALUATED"
    | "FAILED" | "RECOMMENDED" | "APPROVED" | "REJECTED";

export type PlannerMode = "single" | "panel";

export interface FrozenScenario {
    id: string;
    proposal_id: string;
    name: string;
    context_version: string;
    state_version: string;
    disruptions: Record<string, unknown>[];
    active_disruptions: Record<string, unknown>[];
    occurrence_probability: number;
    signal_version_ids: string[];
    provenance: Record<string, unknown>;
}

export interface PlanEvaluation {
    id: string;
    proposal_id: string;
    name: string;
    status: PlanningLifecycle;
    interventions: Record<string, unknown>[];
    planner_metadata: Record<string, unknown>;
    rationale: string;
    assumptions: string[];
    intervention_run_id: string | null;
    intervention_metrics: Record<string, unknown> | null;
    rank: number | null;
    disqualification_reasons: string[];
    ranking_explanation: string | null;
}

export interface PlanningCycle {
    id: string;
    scenario: FrozenScenario;
    generated_scenarios: FrozenScenario[];
    selected_disruption_ids: string[];
    planner_mode: PlannerMode;
    panel_agent_count: number;
    planning_objectives: string[];
    hard_constraints: Record<string, unknown>;
    status: PlanningLifecycle;
    baseline_run_id: string | null;
    baseline_metrics: Record<string, unknown> | null;
    plans: PlanEvaluation[];
    ranking_policy_version: string;
    error_code: string | null;
    error_message: string | null;
}

export interface HypothesisSignal {
    id: string;
    name: string;
    classification: "HYPOTHETICAL";
    signal_type: string;
    payload: Record<string, unknown>;
    occurrence_probability: number;
    rationale: string;
    metadata: Record<string, unknown>;
}

export interface LocalHypothesis extends HypothesisSignal {
    confirmed: boolean;
}

export interface GenerationEntity {
    entity_id: string;
    entity_type: string;
    display_name: string;
    attributes: Record<string, unknown>;
}

export interface CreateCycleInput {
    planning_starts_at: string;
    planning_ends_at: string;
    generation_limit: number;
    planner_mode: PlannerMode;
    panel_agent_count: number;
}

export interface GeneratePlansInput {
    known_entity_ids: string[];
    objectives: string[];
    hard_constraints: Record<string, number>;
    proposal_limit: number;
}
