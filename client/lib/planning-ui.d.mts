import type { PlanEvaluation, PlanningCycle } from "../types/planning";

export const metricOrder: string[];
export function humanize(value: string): string;
export function canGeneratePlans(cycle: PlanningCycle): boolean;
export function canEditScenario(cycle: PlanningCycle): boolean;
export function canSubmitBaseline(cycle: PlanningCycle): boolean;
export function baselineNeedsRefresh(cycle: PlanningCycle): boolean;
export function workflowNeedsAdvance(cycle: PlanningCycle): boolean;
export function canSubmitPlan(plan: PlanEvaluation): boolean;
export function canRefreshPlan(plan: PlanEvaluation): boolean;
export function canRank(cycle: PlanningCycle): boolean;
export function canDecide(plan: PlanEvaluation): boolean;
export function canReject(plan: PlanEvaluation): boolean;
export function orderedPlans(plans: PlanEvaluation[]): PlanEvaluation[];
export function metricValue(metrics: Record<string, unknown> | null, name: string): number | null;
export function metricDelta(baseline: Record<string, unknown> | null,
    intervention: Record<string, unknown> | null, name: string): number | null;
export function formatMetric(value: number | null): string;
export function validPlanningHorizon(startsAt: string, endsAt: string): boolean;
export function apiErrorMessage(payload: unknown, fallback: string): string;
