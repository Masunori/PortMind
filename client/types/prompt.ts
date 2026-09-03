export type AgentName =
    | "filter" | "interpreter" | "planner"
    | "planner_1" | "planner_2" | "planner_3" | "planner_4" | "planner_5";

export interface AgentPrompt {
    agent: AgentName;
    prompt: string;
    is_custom: boolean;
    updated_at: string | null;
}
