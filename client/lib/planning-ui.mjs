/** Pure planning presentation rules shared by the UI and unit tests. */

export const metricOrder = ["late_shipments", "average_delay", "total_cost"];

export function humanize(value) {
    return String(value).replaceAll("_", " ").toLowerCase().replace(/^./, (letter) => letter.toUpperCase());
}

export function canGeneratePlans(cycle) {
    return cycle.baseline_metrics !== null && !["FAILED", "APPROVED", "REJECTED"].includes(cycle.status);
}

export function canEditScenario(cycle) {
    return cycle.status === "PROPOSED" && cycle.baseline_run_id === null;
}

export function canSubmitBaseline(cycle) {
    return canEditScenario(cycle) && cycle.selected_disruption_ids.length > 0;
}

export function baselineNeedsRefresh(cycle) {
    return cycle.baseline_run_id !== null
        && cycle.baseline_metrics === null
        && cycle.status !== "FAILED";
}

export function canSubmitPlan(plan) {
    return plan.status === "VALIDATED" && plan.intervention_run_id === null;
}

export function canRefreshPlan(plan) {
    return plan.status === "RUNNING" && plan.intervention_run_id !== null;
}

export function canRank(cycle) {
    return cycle.plans.some((plan) => plan.status === "EVALUATED");
}

export function canDecide(plan) {
    return plan.status === "RECOMMENDED";
}

export function canReject(plan) {
    return ["VALIDATED", "EVALUATED", "RECOMMENDED"].includes(plan.status);
}

export function orderedPlans(plans) {
    return [...plans].sort((left, right) =>
        (left.rank ?? Number.POSITIVE_INFINITY) - (right.rank ?? Number.POSITIVE_INFINITY)
        || left.proposal_id.localeCompare(right.proposal_id));
}

export function metricValue(metrics, name) {
    const value = metrics?.[name];
    return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function metricDelta(baseline, intervention, name) {
    const baselineValue = metricValue(baseline, name);
    const interventionValue = metricValue(intervention, name);
    return baselineValue === null || interventionValue === null ? null : interventionValue - baselineValue;
}

export function formatMetric(value) {
    return value === null ? "Unavailable" : new Intl.NumberFormat("en-SG", { maximumFractionDigits: 2 }).format(value);
}

export function validPlanningHorizon(startsAt, endsAt) {
    const start = Date.parse(startsAt); const end = Date.parse(endsAt);
    return Number.isFinite(start) && Number.isFinite(end) && end > start;
}

function formatErrorDetail(detail) {
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
        const messages = detail.map((item) => {
            if (!item || typeof item !== "object") return formatErrorDetail(item);
            const message = typeof item.msg === "string" ? item.msg
                : typeof item.message === "string" ? item.message : null;
            const location = Array.isArray(item.loc) ? item.loc.map(String).join(" → ") : null;
            return message ? `${location ? `${location}: ` : ""}${message}` : formatErrorDetail(item);
        }).filter(Boolean);
        return messages.length ? messages.join("; ") : null;
    }
    if (detail && typeof detail === "object") {
        if (typeof detail.message === "string" && detail.message.trim()) {
            return typeof detail.code === "string" && detail.code.trim()
                ? `${detail.message} (${detail.code})` : detail.message;
        }
        try { return JSON.stringify(detail); } catch { return null; }
    }
    return null;
}

export function apiErrorMessage(payload, fallback) {
    const detail = payload && typeof payload === "object" && !Array.isArray(payload)
        && Object.hasOwn(payload, "detail") ? payload.detail : payload;
    return formatErrorDetail(detail) ?? fallback;
}
