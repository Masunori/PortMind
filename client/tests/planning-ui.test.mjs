import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
    apiErrorMessage,
    baselineNeedsRefresh,
    canDecide, canEditScenario, canGeneratePlans, canRank, canRefreshPlan, canReject,
    workflowNeedsAdvance,
    canSubmitBaseline, canSubmitPlan,
    formatMetric, humanize, metricDelta, orderedPlans, validPlanningHorizon,
} from "../lib/planning-ui.mjs";

const plan = (status, overrides = {}) => ({
    proposal_id: "p-1", status, intervention_run_id: null, rank: null, ...overrides,
});
const cycle = (status, overrides = {}) => ({ status, baseline_run_id: null,
    baseline_metrics: null, selected_disruption_ids: ["d-1"], plans: [], ...overrides });

test("lifecycle rules prevent premature planner and human actions", () => {
    assert.equal(canGeneratePlans(cycle("RUNNING")), false);
    assert.equal(canGeneratePlans(cycle("VALIDATED", { baseline_metrics: {} })), true);
    assert.equal(canSubmitPlan(plan("VALIDATED")), true);
    assert.equal(canSubmitPlan(plan("EVALUATED")), false);
    assert.equal(canRefreshPlan(plan("RUNNING", { intervention_run_id: "run-1" })), true);
    assert.equal(canDecide(plan("EVALUATED")), false);
    assert.equal(canDecide(plan("RECOMMENDED")), true);
    assert.equal(canReject(plan("VALIDATED")), true);
    assert.equal(canReject(plan("RUNNING")), false);
});

test("scenario review and baseline submission are separate lifecycle actions", () => {
    assert.equal(canEditScenario(cycle("PROPOSED")), true);
    assert.equal(canSubmitBaseline(cycle("PROPOSED")), true);
    assert.equal(canSubmitBaseline(cycle("PROPOSED", { selected_disruption_ids: [] })), false);
    assert.equal(canEditScenario(cycle("RUNNING", { baseline_run_id: "run-1" })), false);
    assert.equal(baselineNeedsRefresh(cycle("RUNNING", { baseline_run_id: "run-1" })), true);
    assert.equal(baselineNeedsRefresh(cycle("VALIDATED", {
        baseline_run_id: "run-1", baseline_metrics: {},
    })), false);
    assert.equal(baselineNeedsRefresh(cycle("FAILED", { baseline_run_id: "run-1" })), false);
});

test("post-simulation planning has no manual generation or entity-ID form", () => {
    const source = readFileSync(new URL("../components/PlanningConsole.tsx", import.meta.url), "utf8");
    assert.doesNotMatch(source, /Known entity IDs, comma-separated/);
    assert.doesNotMatch(source, /Generate intervention alternatives/);
    assert.doesNotMatch(source, /\/proposals`/);
    assert.match(source, /Authoritative simulation result/);
    assert.match(source, /All mitigation plans/);
});

test("cycle creation lets the user choose a single planner or planner panel", () => {
    const source = readFileSync(new URL("../components/PlanningConsole.tsx", import.meta.url), "utf8");
    assert.match(source, /name="planner_mode"/);
    assert.match(source, /<option value="single">Single planner<\/option>/);
    assert.match(source, /<option value="panel">Panel of planners<\/option>/);
    assert.match(source, /planner_mode: String\(form\.get\("planner_mode"\)/);
    assert.match(source, /name="panel_agent_count"/);
    assert.match(source, /\[1, 2, 3, 4, 5\]/);
    assert.match(source, /panel_agent_count: Number\(form\.get\("panel_agent_count"\)/);
});

test("ranking availability and ordering ignore incomplete rank values", () => {
    assert.equal(canRank(cycle("VALIDATED", { plans: [plan("RUNNING")] })), false);
    assert.equal(canRank(cycle("VALIDATED", { plans: [plan("EVALUATED")] })), true);
    const ordered = orderedPlans([
        plan("EVALUATED", { proposal_id: "b", rank: null }),
        plan("RECOMMENDED", { proposal_id: "a", rank: 1 }),
    ]);
    assert.deepEqual(ordered.map((item) => item.proposal_id), ["a", "b"]);
});

test("workflow advancement continues through planning and stops at recommendation", () => {
    assert.equal(workflowNeedsAdvance(cycle("RUNNING", { baseline_run_id: "base-1" })), true);
    assert.equal(workflowNeedsAdvance(cycle("VALIDATED", { baseline_metrics: { late_shipments: 2 }, plans: [] })), true);
    assert.equal(workflowNeedsAdvance(cycle("VALIDATED", { baseline_metrics: {}, plans: [plan("VALIDATED")] })), true);
    assert.equal(workflowNeedsAdvance(cycle("EVALUATED", { baseline_metrics: {}, plans: [] })), false);
    assert.equal(workflowNeedsAdvance(cycle("RECOMMENDED", { baseline_metrics: {}, plans: [plan("RECOMMENDED")] })), false);
});

test("authoritative metric deltas require numeric values on both runs", () => {
    assert.equal(metricDelta({ total_cost: 10 }, { total_cost: 7 }, "total_cost"), -3);
    assert.equal(metricDelta({ total_cost: 10 }, { total_cost: "claimed" }, "total_cost"), null);
    assert.equal(formatMetric(null), "Unavailable");
    assert.equal(formatMetric(1234.567), "1,234.57");
    assert.equal(humanize("STALE_STATE"), "Stale state");
});

test("planning horizons must be valid and ordered", () => {
    assert.equal(validPlanningHorizon("2026-08-28", "2026-09-27"), true);
    assert.equal(validPlanningHorizon("2026-09-27", "2026-08-28"), false);
    assert.equal(validPlanningHorizon("not-a-date", "2026-09-27"), false);
});

test("API errors render structured details as human-readable messages", () => {
    assert.equal(apiErrorMessage({ detail: { code: "CLIENT_UNAVAILABLE",
        message: "Client is unavailable" } }, "Fallback"),
    "Client is unavailable (CLIENT_UNAVAILABLE)");
    assert.equal(apiErrorMessage({ detail: "Planning horizon is invalid" }, "Fallback"),
        "Planning horizon is invalid");
    assert.equal(apiErrorMessage({ detail: [{ loc: ["body", "generation_limit"],
        msg: "Input should be less than or equal to 20" }] }, "Fallback"),
    "body → generation_limit: Input should be less than or equal to 20");
    assert.equal(apiErrorMessage(null, "Risk generation failed (500)"),
        "Risk generation failed (500)");
});
