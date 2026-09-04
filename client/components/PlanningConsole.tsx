"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
    apiErrorMessage,
    baselineNeedsRefresh,
    canDecide,
    canEditScenario,
    canReject,
    canSubmitBaseline,
    formatMetric,
    humanize,
    metricDelta,
    metricOrder,
    orderedPlans,
    validPlanningHorizon,
    workflowNeedsAdvance,
} from "@/lib/planning-ui.mjs";
import {
    hypothesisStorageKey,
    mergeHypotheses,
    parseHypotheses,
    removeHypothesis,
    toggleHypothesis,
} from "@/lib/hypothesis-store.mjs";
import type {
    LocalHypothesis,
    GenerationEntity,
    PlanEvaluation,
    PlanningCycle,
    PlanningLifecycle,
} from "@/types/planning";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const inputClass =
    "rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100";

function StatusBadge({ status }: { status: PlanningLifecycle }) {
    const tone =
        status === "FAILED"
            ? "border-red-800 bg-red-950 text-red-300"
            : ["RECOMMENDED", "APPROVED"].includes(status)
              ? "border-emerald-800 bg-emerald-950 text-emerald-300"
              : status === "REJECTED"
                ? "border-slate-700 bg-slate-950 text-slate-400"
                : "border-sky-800 bg-sky-950 text-sky-300";
    return (
        <span
            className={`rounded-full border px-2.5 py-1 text-xs font-medium ${tone}`}
        >
            {humanize(status)}
        </span>
    );
}

function JsonDetails({ label, value }: { label: string; value: unknown }) {
    return (
        <details className="mt-3">
            <summary className="cursor-pointer text-xs font-medium text-sky-300">
                {label}
            </summary>
            <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-300">
                {JSON.stringify(value, null, 2)}
            </pre>
        </details>
    );
}

function MetricCell({
    baseline,
    plan,
    name,
}: {
    baseline: Record<string, unknown> | null;
    plan: Record<string, unknown> | null;
    name: string;
}) {
    const value =
        typeof plan?.[name] === "number" ? (plan[name] as number) : null;
    const delta = metricDelta(baseline, plan, name);
    return (
        <td className="px-3 py-3 text-right">
            <span>{formatMetric(value)}</span>
            {delta !== null && (
                <span
                    className={`ml-2 text-xs ${delta <= 0 ? "text-emerald-300" : "text-amber-300"}`}
                >
                    {delta > 0 ? "+" : ""}
                    {formatMetric(delta)}
                </span>
            )}
        </td>
    );
}

function Comparison({ cycle }: { cycle: PlanningCycle }) {
    const plans = orderedPlans(cycle.plans);
    if (!cycle.baseline_metrics) return null;
    return (
        <section
            className="mt-5 min-w-0 max-w-full"
            aria-labelledby={`comparison-${cycle.id}`}
        >
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h3 id={`comparison-${cycle.id}`} className="font-semibold">
                        Authoritative comparison
                    </h3>
                    <p className="text-xs text-slate-500">
                        Policy {cycle.ranking_policy_version}. Lower is better;
                        missing metrics are ineligible.
                    </p>
                </div>
            </div>
            <div className="mt-3 max-w-full overflow-x-auto rounded-xl border border-slate-800">
                <table className="w-full min-w-[760px] text-left text-sm">
                    <thead className="bg-slate-950 text-xs uppercase text-slate-500">
                        <tr>
                            <th className="px-3 py-3">Plan</th>
                            {metricOrder.map((name) => (
                                <th key={name} className="px-3 py-3 text-right">
                                    {humanize(name)}
                                </th>
                            ))}
                            <th className="px-3 py-3">Eligibility</th>
                            <th className="px-3 py-3 text-right">Rank</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                        <tr>
                            <th className="px-3 py-3 font-medium">Baseline</th>
                            {metricOrder.map((name) => (
                                <MetricCell
                                    key={name}
                                    baseline={null}
                                    plan={cycle.baseline_metrics}
                                    name={name}
                                />
                            ))}
                            <td className="px-3 py-3 text-slate-500">
                                Reference
                            </td>
                            <td className="px-3 py-3 text-right">—</td>
                        </tr>
                        {plans.map((plan) => (
                            <tr key={plan.id}>
                                <th className="px-3 py-3 font-medium">
                                    {plan.name}
                                </th>
                                {metricOrder.map((name) => (
                                    <MetricCell
                                        key={name}
                                        baseline={cycle.baseline_metrics}
                                        plan={plan.intervention_metrics}
                                        name={name}
                                    />
                                ))}
                                <td className="px-3 py-3">
                                    {plan.disqualification_reasons.length ? (
                                        <span className="text-red-300">
                                            Disqualified
                                        </span>
                                    ) : plan.intervention_metrics ? (
                                        <span className="text-emerald-300">
                                            Eligible
                                        </span>
                                    ) : (
                                        <span className="text-slate-500">
                                            Incomplete
                                        </span>
                                    )}
                                </td>
                                <td className="px-3 py-3 text-right">
                                    {plan.rank ?? "—"}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </section>
    );
}

function PlanCard({
    cycle,
    plan,
    busy,
    mutate,
}: {
    cycle: PlanningCycle;
    plan: PlanEvaluation;
    busy: string | null;
    mutate: (
        action: string,
        path: string,
        confirmation?: string,
    ) => Promise<PlanningCycle | null>;
}) {
    const locked = busy !== null;
    return (
        <article className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <div className="flex flex-wrap items-center gap-2">
                        <h4 className="font-semibold">{plan.name}</h4>
                        <StatusBadge status={plan.status} />
                        {plan.rank && (
                            <span className="text-xs text-slate-400">
                                Rank {plan.rank}
                            </span>
                        )}
                    </div>
                    <p className="mt-1 font-mono text-[11px] text-slate-600">
                        {plan.proposal_id}
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    {canDecide(plan) && (
                        <button
                            disabled={locked}
                            onClick={() =>
                                void mutate(
                                    `approve-${plan.id}`,
                                    `/api/planning/cycles/${cycle.id}/plans/${plan.id}/approve`,
                                    "Approve this recommendation? Approval records a planning decision and does not execute interventions in the connected system.",
                                )
                            }
                            className="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold"
                        >
                            Approve
                        </button>
                    )}
                    {canReject(plan) && (
                        <button
                            disabled={locked}
                            onClick={() =>
                                void mutate(
                                    `reject-${plan.id}`,
                                    `/api/planning/cycles/${cycle.id}/plans/${plan.id}/reject`,
                                    "Reject this proposal? Its provenance and simulation history will be retained.",
                                )
                            }
                            className="rounded-lg border border-red-800 px-3 py-2 text-xs text-red-300"
                        >
                            Reject
                        </button>
                    )}
                </div>
            </div>
            <div className="mt-4 grid gap-4 text-sm lg:grid-cols-2">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-violet-300">
                        Planner rationale · qualitative
                    </p>
                    <p className="mt-1 text-slate-300">{plan.rationale}</p>
                    {plan.assumptions.length > 0 && (
                        <ul className="mt-2 list-disc pl-5 text-xs text-slate-400">
                            {plan.assumptions.map((item) => (
                                <li key={item}>{item}</li>
                            ))}
                        </ul>
                    )}
                </div>
                <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-emerald-300">
                        Deterministic evaluation
                    </p>
                    <p className="mt-1 text-slate-300">
                        {plan.ranking_explanation ??
                            "Available after authoritative results are ranked."}
                    </p>
                    {plan.disqualification_reasons.map((reason) => (
                        <p key={reason} className="mt-1 text-xs text-red-300">
                            {reason}
                        </p>
                    ))}
                </div>
            </div>
            {plan.intervention_run_id && (
                <p className="mt-3 text-xs text-slate-500">
                    Intervention run{" "}
                    <span className="font-mono text-slate-400">
                        {plan.intervention_run_id}
                    </span>{" "}
                    · baseline{" "}
                    <span className="font-mono text-slate-400">
                        {cycle.baseline_run_id}
                    </span>
                </p>
            )}
            <JsonDetails
                label="Exact client-validated interventions"
                value={plan.interventions}
            />
            <JsonDetails
                label="Planner provenance"
                value={plan.planner_metadata}
            />
        </article>
    );
}

function CycleCard({ initialCycle }: { initialCycle: PlanningCycle }) {
    const router = useRouter();
    const [cycle, setCycle] = useState(initialCycle);
    const [busy, setBusy] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const [selection, setSelection] = useState<string[]>(
        initialCycle.selected_disruption_ids,
    );

    const mutate = useCallback(
        async function mutate(
            action: string,
            path: string,
            confirmation?: string,
            body?: unknown,
        ): Promise<PlanningCycle | null> {
            if (confirmation && !window.confirm(confirmation)) return null;
            setBusy(action);
            setError(null);
            setNotice(null);
            try {
                const response = await fetch(`${apiUrl}${path}`, {
                    method: "POST",
                    headers:
                        body === undefined
                            ? undefined
                            : { "Content-Type": "application/json" },
                    body: body === undefined ? undefined : JSON.stringify(body),
                });
                const payload = (await response.json().catch(() => null)) as
                    | PlanningCycle
                    | { detail?: string }
                    | null;
                if (!response.ok)
                    throw new Error(
                        apiErrorMessage(
                            payload,
                            `Request failed (${response.status})`,
                        ),
                    );
                const updated = payload as PlanningCycle;
                setCycle(updated);
                setSelection(updated.selected_disruption_ids);
                setNotice("Workflow updated.");
                router.refresh();
                return updated;
            } catch (caught) {
                setError(
                    caught instanceof Error ? caught.message : "Request failed",
                );
                return null;
            } finally {
                setBusy(null);
            }
        },
        [router],
    );

    async function runReviewedScenario() {
        const reviewed = await mutate(
            "review",
            `/api/planning/cycles/${cycle.id}/scenario`,
            undefined,
            { disruption_ids: selection },
        );
        if (reviewed)
            await mutate(
                "baseline-submit",
                `/api/planning/cycles/${cycle.id}/baseline/submit`,
            );
    }

    const baselinePending = baselineNeedsRefresh(cycle);
    const workflowPending = workflowNeedsAdvance(cycle);

    useEffect(() => {
        if (!workflowPending || busy !== null) return;
        const timeout = window.setTimeout(() => {
            void mutate(
                "workflow-auto-advance",
                `/api/planning/cycles/${cycle.id}/advance`,
            );
        }, 5000);
        return () => window.clearTimeout(timeout);
    }, [workflowPending, busy, cycle.id, mutate]);
    const disruptions = [
        ...new Map(
            cycle.generated_scenarios.flatMap((scenario) =>
                scenario.disruptions.map(
                    (item) => [String(item.disruption_id), item] as const,
                ),
            ),
        ).values(),
    ];
    return (
        <article
            id={cycle.id}
            className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-xl shadow-black/10"
        >
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-xl font-semibold">
                            {cycle.scenario.name}
                        </h2>
                        <StatusBadge status={cycle.status} />
                    </div>
                    <p className="mt-2 text-sm text-slate-400">
                        Risk probability{" "}
                        {Math.round(
                            cycle.scenario.occurrence_probability * 100,
                        )}
                        % · {cycle.scenario.disruptions.length} disruption
                        {cycle.scenario.disruptions.length === 1 ? "" : "s"}
                    </p>
                    <p className="mt-1 font-mono text-[11px] text-slate-600">
                        {cycle.id}
                    </p>
                </div>
                {baselinePending && (
                    <button
                        disabled={busy !== null}
                        onClick={() =>
                            void mutate(
                                "baseline",
                                `/api/planning/cycles/${cycle.id}/baseline/refresh`,
                            )
                        }
                        className="rounded-lg border border-sky-800 px-3 py-2 text-sm text-sky-300"
                    >
                        {busy === "baseline"
                            ? "Refreshing…"
                            : "Refresh baseline"}
                    </button>
                )}
            </div>
            {cycle.baseline_run_id === null && (
                <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="rounded-lg bg-slate-950 p-3">
                        <p className="text-xs text-slate-500">
                            Context version
                        </p>
                        <p className="mt-1 truncate font-mono text-xs text-sky-300">
                            {cycle.scenario.context_version}
                        </p>
                    </div>
                    <div className="rounded-lg bg-slate-950 p-3">
                        <p className="text-xs text-slate-500">State version</p>
                        <p className="mt-1 truncate font-mono text-xs text-sky-300">
                            {cycle.scenario.state_version}
                        </p>
                    </div>
                    <div className="rounded-lg bg-slate-950 p-3">
                        <p className="text-xs text-slate-500">Baseline run</p>
                        <p className="mt-1 truncate font-mono text-xs text-slate-300">
                            {cycle.baseline_run_id ?? "Not submitted"}
                        </p>
                    </div>
                    <div className="rounded-lg bg-slate-950 p-3">
                        <p className="text-xs text-slate-500">Ranking policy</p>
                        <p className="mt-1 font-mono text-xs text-slate-300">
                            {cycle.ranking_policy_version}
                        </p>
                    </div>
                </div>
            )}
            {error && (
                <div
                    role="alert"
                    aria-live="assertive"
                    className="mt-4 rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-300"
                >
                    <p className="font-semibold">Action request failed</p>
                    <p>{error}</p>
                    <p className="mt-1 text-xs text-red-400">
                        This is a temporary browser request error and is not
                        saved as part of the planning cycle.
                    </p>
                </div>
            )}
            {notice && (
                <p
                    aria-live="polite"
                    className="mt-4 rounded-lg border border-emerald-800 bg-emerald-950 p-3 text-sm text-emerald-300"
                >
                    {notice}
                </p>
            )}
            {cycle.status === "FAILED" && (
                <div className="mt-4 rounded-lg border border-red-800 bg-red-950/60 p-3 text-sm text-red-300">
                    <p className="font-semibold">
                        Workflow failure · saved with this cycle
                    </p>
                    <p>
                        {cycle.error_message ??
                            cycle.error_code ??
                            "The authoritative simulation failed."}
                    </p>
                    <p className="mt-1 text-xs">
                        Historical inputs remain frozen. Start a new cycle after
                        correcting state in the connected system.
                    </p>
                </div>
            )}
            {cycle.status !== "FAILED" && cycle.error_message && (
                <div className="mt-4 rounded-lg border border-amber-800 bg-amber-950/60 p-3 text-sm text-amber-300">
                    <p className="font-semibold">
                        Workflow warning · saved with this cycle
                    </p>
                    <p>{cycle.error_message}</p>
                    <p className="mt-1 text-xs text-amber-400">
                        The completed simulation result remains valid. This
                        warning records a later workflow step that could not
                        complete.
                    </p>
                </div>
            )}
            {canEditScenario(cycle) && (
                <section className="mt-5 rounded-xl border border-sky-900 bg-sky-950/20 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                            <h3 className="font-semibold">
                                Confirm or remove risk signals
                            </h3>
                            <p className="mt-1 text-xs text-slate-400">
                                {cycle.generated_scenarios.length} scenario
                                proposal
                                {cycle.generated_scenarios.length === 1
                                    ? ""
                                    : "s"}{" "}
                                produced {disruptions.length} unique disruption
                                {disruptions.length === 1 ? "" : "s"}. Checked
                                signals are confirmed for simulation; clear a
                                checkbox to remove one.
                            </p>
                        </div>
                        <button
                            disabled={
                                busy !== null ||
                                selection.length === 0 ||
                                selection.length > 20 ||
                                !canSubmitBaseline({
                                    ...cycle,
                                    selected_disruption_ids: selection,
                                })
                            }
                            onClick={() => void runReviewedScenario()}
                            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold disabled:opacity-40"
                        >
                            {busy ? "Working…" : "Simulate"}
                        </button>
                    </div>
                    <div className="mt-4 grid gap-2 lg:grid-cols-2">
                        {disruptions.map((item) => {
                            const id = String(item.disruption_id);
                            return (
                                <label
                                    key={id}
                                    className="flex cursor-pointer gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3"
                                >
                                    <input
                                        type="checkbox"
                                        checked={selection.includes(id)}
                                        onChange={(event) =>
                                            setSelection((current) =>
                                                event.target.checked
                                                    ? [...current, id]
                                                    : current.filter(
                                                          (value) =>
                                                              value !== id,
                                                      ),
                                            )
                                        }
                                        className="mt-1"
                                    />
                                    <span>
                                        <span className="block text-sm font-medium">
                                            {humanize(
                                                String(
                                                    item.type ?? "disruption",
                                                ),
                                            )}
                                        </span>
                                        <span className="block text-xs text-slate-500">
                                            {humanize(
                                                String(
                                                    item.classification ??
                                                        "unknown",
                                                ),
                                            )}{" "}
                                            · {id}
                                        </span>
                                    </span>
                                </label>
                            );
                        })}
                    </div>
                    {selection.length > 20 && (
                        <p role="alert" className="mt-3 text-xs text-red-300">
                            Select no more than 20 disruptions.
                        </p>
                    )}
                </section>
            )}
            {cycle.baseline_metrics && (
                <section className="mt-5 rounded-xl border border-emerald-900 bg-emerald-950/20 p-4">
                    <h3 className="font-semibold text-emerald-300">
                        Authoritative simulation result
                    </h3>
                    <p className="mt-1 text-xs text-slate-400">
                        Returned by the connected client and supplied unchanged
                        to the planning agent.
                    </p>
                    <JsonDetails
                        label="Baseline metrics"
                        value={cycle.baseline_metrics}
                    />
                </section>
            )}
            {cycle.baseline_run_id === null && (
                <JsonDetails
                    label="Frozen scenario and disruption provenance"
                    value={{
                        complete_scenario: cycle.scenario.disruptions,
                        active_simulator_inputs:
                            cycle.scenario.active_disruptions,
                        signal_version_ids: cycle.scenario.signal_version_ids,
                        provenance: cycle.scenario.provenance,
                    }}
                />
            )}
            {cycle.plans.length > 0 && (
                <section className="mt-6 space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                            <h3 className="font-semibold">
                                All mitigation plans
                            </h3>
                            <p className="text-xs text-slate-500">
                                {cycle.planner_mode === "panel"
                                    ? `Panel of ${cycle.panel_agent_count} ${cycle.panel_agent_count === 1 ? "planner" : "planners"}`
                                    : "Single planner"}{" "}
                                · {cycle.plans.length} proposal
                                {cycle.plans.length === 1 ? "" : "s"}
                            </p>
                        </div>
                        {workflowPending && (
                            <span className="text-xs text-sky-300">
                                Simulating and ranking automatically…
                            </span>
                        )}
                    </div>
                    {orderedPlans(cycle.plans).map((plan) => (
                        <PlanCard
                            key={plan.id}
                            cycle={cycle}
                            plan={plan}
                            busy={busy}
                            mutate={mutate}
                        />
                    ))}
                </section>
            )}
            <Comparison cycle={cycle} />
        </article>
    );
}

export default function PlanningConsole({
    initialCycles,
    entityScope: initialEntityScope,
    connected,
}: {
    initialCycles: PlanningCycle[];
    entityScope: GenerationEntity[];
    connected: boolean;
}) {
    const router = useRouter();
    const [creating, setCreating] = useState(false);
    const [plannerMode, setPlannerMode] = useState<"single" | "panel">(
        "single",
    );
    const [generatingHypotheses, setGeneratingHypotheses] = useState(false);
    const [hypothesesLoaded, setHypothesesLoaded] = useState(false);
    const [hypotheses, setHypotheses] = useState<LocalHypothesis[]>([]);
    const [entityScope, setEntityScope] = useState(initialEntityScope);
    const [entityResults, setEntityResults] = useState<GenerationEntity[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [selectedCycleId, setSelectedCycleId] = useState<string | null>(
        initialCycles.at(-1)?.id ?? null,
    );
    const [defaultHorizon] = useState(() => {
        const start = new Date();
        const end = new Date(start);
        end.setUTCDate(end.getUTCDate() + 30);
        return {
            start: start.toISOString().slice(0, 10),
            end: end.toISOString().slice(0, 10),
        };
    });
    useEffect(() => {
        const timer = window.setTimeout(() => {
            setHypotheses(
                parseHypotheses(
                    window.localStorage.getItem(hypothesisStorageKey),
                ),
            );
            setHypothesesLoaded(true);
        }, 0);
        return () => window.clearTimeout(timer);
    }, []);
    useEffect(() => {
        if (hypothesesLoaded)
            window.localStorage.setItem(
                hypothesisStorageKey,
                JSON.stringify(hypotheses),
            );
    }, [hypotheses, hypothesesLoaded]);
    const selectedCycle =
        initialCycles.find((cycle) => cycle.id === selectedCycleId) ??
        initialCycles.at(-1) ??
        null;
    const effectiveSelectedCycleId = selectedCycle?.id ?? null;

    async function searchEntities(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setError(null);
        try {
            const response = await fetch(
                `${apiUrl}/api/planning/cycles/entities/search`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        query: String(form.get("entity_query") ?? ""),
                        limit: 10,
                    }),
                },
            );
            const payload = (await response.json().catch(() => null)) as
                | GenerationEntity[]
                | { detail?: string }
                | null;
            if (!response.ok || !Array.isArray(payload))
                throw new Error(
                    apiErrorMessage(
                        payload,
                        `Entity search failed (${response.status})`,
                    ),
                );
            setEntityResults(payload);
        } catch (caught) {
            setError(
                caught instanceof Error
                    ? caught.message
                    : "Entity search failed",
            );
        }
    }

    function addEntity(item: GenerationEntity) {
        setEntityScope((current) =>
            [
                ...current.filter(
                    (entity) => entity.entity_id !== item.entity_id,
                ),
                item,
            ].sort((left, right) =>
                left.entity_id.localeCompare(right.entity_id),
            ),
        );
    }

    async function generateHypotheses(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setGeneratingHypotheses(true);
        setError(null);
        try {
            const response = await fetch(
                `${apiUrl}/api/planning/cycles/hypotheses/generate`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        prompt: String(form.get("hypothesis_prompt") ?? ""),
                        entity_scope: entityScope,
                        generation_limit: Number(
                            form.get("hypothesis_limit") ?? 3,
                        ),
                    }),
                },
            );
            const payload = (await response.json().catch(() => null)) as {
                hypotheses?: LocalHypothesis[];
                detail?: string;
            } | null;
            if (!response.ok)
                throw new Error(
                    apiErrorMessage(
                        payload,
                        `Hypothesis generation failed (${response.status})`,
                    ),
                );
            setHypotheses((current) =>
                mergeHypotheses(current, payload?.hypotheses ?? []),
            );
        } catch (caught) {
            setError(
                caught instanceof Error
                    ? caught.message
                    : "Hypothesis generation failed",
            );
        } finally {
            setGeneratingHypotheses(false);
        }
    }
    async function create(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setCreating(true);
        setError(null);
        const planningStartsAt = String(form.get("planning_starts_at") ?? "");
        const planningEndsAt = String(form.get("planning_ends_at") ?? "");
        if (!validPlanningHorizon(planningStartsAt, planningEndsAt)) {
            setError("Planning horizon end must be after its start.");
            setCreating(false);
            return;
        }
        const constraints = Object.fromEntries(
            metricOrder.flatMap((name) => {
                const value = String(form.get(`cycle_${name}`) ?? "").trim();
                return value ? [[name, Number(value)]] : [];
            }),
        );
        try {
            const response = await fetch(`${apiUrl}/api/planning/cycles`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    planning_starts_at: planningStartsAt,
                    planning_ends_at: planningEndsAt,
                    generation_limit: Number(form.get("generation_limit") ?? 5),
                    planner_mode: String(form.get("planner_mode") ?? "single"),
                    panel_agent_count: Number(
                        form.get("panel_agent_count") ?? 3,
                    ),
                    confirmed_hypotheses: hypotheses
                        .filter((item) => item.confirmed)
                        .map((item) => ({
                            id: item.id,
                            name: item.name,
                            classification: item.classification,
                            signal_type: item.signal_type,
                            payload: item.payload,
                            occurrence_probability: item.occurrence_probability,
                            rationale: item.rationale,
                            metadata: item.metadata,
                        })),
                    entity_scope: entityScope,
                    objectives: String(form.get("cycle_objectives") ?? "")
                        .split(",")
                        .map((item) => item.trim())
                        .filter(Boolean),
                    hard_constraints: constraints,
                }),
            });
            const payload = (await response.json().catch(() => null)) as {
                id?: string;
                detail?: string;
            } | null;
            if (!response.ok)
                throw new Error(
                    apiErrorMessage(
                        payload,
                        `Risk generation failed (${response.status})`,
                    ),
                );
            if (payload?.id) setSelectedCycleId(payload.id);
            router.refresh();
        } catch (caught) {
            setError(
                caught instanceof Error
                    ? caught.message
                    : "Risk generation failed",
            );
        } finally {
            setCreating(false);
        }
    }
    return (
        <div className="space-y-6">
            {error && (
                <p
                    role="alert"
                    className="rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-300"
                >
                    {error}
                </p>
            )}
            <section className="rounded-2xl border border-violet-900 bg-slate-900 p-5">
                <h2 className="font-semibold">
                    Prompt hypothetical risk signals
                </h2>
                <p className="mt-1 text-sm text-slate-400">
                    Generated hypotheses stay in this browser until you confirm
                    them for a scenario. They are not written to the signal
                    database.
                </p>
                <form
                    onSubmit={searchEntities}
                    className="mt-4 flex flex-wrap gap-2"
                >
                    <input
                        required
                        name="entity_query"
                        placeholder="Search client entities"
                        className={`${inputClass} min-w-72 flex-1`}
                    />
                    <button
                        disabled={!connected}
                        className="rounded-lg bg-slate-700 px-4 py-2 text-sm font-semibold disabled:opacity-40"
                    >
                        Search entities
                    </button>
                </form>
                {entityResults.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                        {entityResults.map((item) => (
                            <button
                                key={item.entity_id}
                                type="button"
                                onClick={() => addEntity(item)}
                                className="rounded-full border border-violet-800 px-3 py-1 text-xs text-violet-200"
                            >
                                Add {item.display_name} ({item.entity_type})
                            </button>
                        ))}
                    </div>
                )}
                <div
                    className="mt-3 flex flex-wrap gap-2"
                    aria-label="Included entities"
                >
                    {entityScope.map((item) => (
                        <span
                            key={item.entity_id}
                            className="rounded-full bg-violet-950 px-3 py-1 text-xs text-violet-200"
                        >
                            {item.display_name} · {item.entity_type}
                            <button
                                type="button"
                                aria-label={`Remove ${item.display_name}`}
                                onClick={() =>
                                    setEntityScope((current) =>
                                        current.filter(
                                            (entity) =>
                                                entity.entity_id !==
                                                item.entity_id,
                                        ),
                                    )
                                }
                                className="ml-2 text-red-300"
                            >
                                ×
                            </button>
                        </span>
                    ))}
                </div>
                <form
                    onSubmit={generateHypotheses}
                    className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto_auto]"
                >
                    <label className="grid gap-1 text-xs text-slate-400">
                        Planning prompt
                        <textarea
                            required
                            name="hypothesis_prompt"
                            rows={3}
                            placeholder="Generate plausible scenarios that could increase company lead time"
                            className={inputClass}
                        />
                    </label>
                    <label className="grid content-start gap-1 text-xs text-slate-400">
                        Limit
                        <input
                            name="hypothesis_limit"
                            type="number"
                            min="1"
                            max="10"
                            defaultValue="3"
                            className={`${inputClass} w-24`}
                        />
                    </label>
                    <button
                        disabled={!connected || generatingHypotheses}
                        className="self-end rounded-lg bg-violet-700 px-4 py-2 text-sm font-semibold disabled:opacity-40"
                    >
                        {generatingHypotheses
                            ? "Generating…"
                            : "Generate hypotheses"}
                    </button>
                </form>
                {hypotheses.length > 0 && (
                    <div className="mt-4 grid gap-2 lg:grid-cols-2">
                        {hypotheses.map((item) => (
                            <article
                                key={item.id}
                                className="rounded-lg border border-slate-800 bg-slate-950 p-3"
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <label className="flex gap-2 text-sm font-medium">
                                        <input
                                            type="checkbox"
                                            checked={item.confirmed}
                                            onChange={() =>
                                                setHypotheses((current) =>
                                                    toggleHypothesis(
                                                        current,
                                                        item.id,
                                                    ),
                                                )
                                            }
                                        />
                                        Confirm {item.name}
                                    </label>
                                    <button
                                        onClick={() =>
                                            setHypotheses((current) =>
                                                removeHypothesis(
                                                    current,
                                                    item.id,
                                                ),
                                            )
                                        }
                                        className="text-xs text-red-300"
                                    >
                                        Remove
                                    </button>
                                </div>
                                <p className="mt-2 text-xs text-slate-400">
                                    {item.rationale}
                                </p>
                                <p className="mt-2 font-mono text-[11px] text-violet-300">
                                    {item.signal_type} ·{" "}
                                    {Math.round(
                                        item.occurrence_probability * 100,
                                    )}
                                    %
                                </p>
                                <JsonDetails
                                    label="Proposed payload"
                                    value={item.payload}
                                />
                            </article>
                        ))}
                    </div>
                )}
            </section>
            <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div>
                    <h2 className="font-semibold">Generate risk scenarios</h2>
                    <p className="mt-1 max-w-3xl text-sm text-slate-400">
                        The risk agent groups compatible observed, forecast, and
                        confirmed hypothetical disruptions. Generation creates a
                        review draft and does not invoke simulation.
                    </p>
                </div>
                <form onSubmit={create} className="mt-5 grid gap-4">
                    <div
                        className={`grid items-start gap-3 sm:grid-cols-2 ${plannerMode === "panel" ? "xl:grid-cols-[minmax(10rem,1fr)_minmax(10rem,1fr)_8rem_minmax(14rem,1.35fr)_minmax(10rem,0.8fr)]" : "xl:grid-cols-[minmax(10rem,1fr)_minmax(10rem,1fr)_8rem_minmax(14rem,1.35fr)]"}`}
                    >
                        <label className="grid gap-1 text-xs text-slate-400">
                            Horizon start
                            <input
                                required
                                name="planning_starts_at"
                                type="date"
                                defaultValue={defaultHorizon.start}
                                className={`${inputClass} w-full`}
                            />
                        </label>
                        <label className="grid gap-1 text-xs text-slate-400">
                            Horizon end
                            <input
                                required
                                name="planning_ends_at"
                                type="date"
                                defaultValue={defaultHorizon.end}
                                className={`${inputClass} w-full`}
                            />
                        </label>
                        <label className="grid gap-1 text-xs text-slate-400">
                            Scenario limit
                            <input
                                name="generation_limit"
                                type="number"
                                min="1"
                                max="20"
                                defaultValue="5"
                                className={`${inputClass} w-full`}
                            />
                        </label>
                        <label className="grid gap-1 text-xs text-slate-400">
                            Planner mode
                            <select
                                name="planner_mode"
                                value={plannerMode}
                                onChange={(event) =>
                                    setPlannerMode(
                                        event.target.value as
                                            | "single"
                                            | "panel",
                                    )
                                }
                                aria-describedby="planner-mode-help"
                                className={`${inputClass} w-full`}
                            >
                                <option value="single">Single planner</option>
                                <option value="panel">Panel of planners</option>
                            </select>
                            <span
                                id="planner-mode-help"
                                className="text-[11px] leading-4 text-slate-500"
                            >
                                A panel returns separate continuity, cost, and
                                resilience proposals.
                            </span>
                        </label>
                        {plannerMode === "panel" && (
                            <label className="grid gap-1 text-xs text-slate-400">
                                Panel agents
                                <select
                                    name="panel_agent_count"
                                    defaultValue="3"
                                    className={`${inputClass} w-full`}
                                >
                                    {[1, 2, 3, 4, 5].map((count) => (
                                        <option key={count} value={count}>
                                            {count}{" "}
                                            {count === 1 ? "agent" : "agents"}
                                        </option>
                                    ))}
                                </select>
                                <span className="text-[11px] leading-4 text-slate-500">
                                    Uses panel prompts 1 through the selected
                                    count.
                                </span>
                            </label>
                        )}
                    </div>
                    <div className="grid items-end gap-3 md:grid-cols-2 xl:grid-cols-[minmax(20rem,2fr)_repeat(3,minmax(9rem,1fr))]">
                        <label className="grid gap-1 text-xs text-slate-400">
                            Objectives
                            <input
                                name="cycle_objectives"
                                defaultValue="minimize late shipments, minimize average delay, minimize total cost"
                                className={`${inputClass} w-full`}
                            />
                        </label>
                        {metricOrder.map((name) => (
                            <label
                                key={name}
                                className="grid gap-1 text-xs text-slate-400"
                            >
                                Max {humanize(name)}
                                <input
                                    name={`cycle_${name}`}
                                    type="number"
                                    min="0"
                                    step="any"
                                    className={`${inputClass} w-full`}
                                />
                            </label>
                        ))}
                    </div>
                    <div>
                        <button
                            disabled={!connected || creating}
                            title={
                                !connected
                                    ? "Reconnect the authoritative client first"
                                    : undefined
                            }
                            className="rounded-lg bg-sky-600 px-5 py-2.5 text-sm font-semibold disabled:opacity-40"
                        >
                            {creating
                                ? "Generating…"
                                : `Generate scenarios (${hypotheses.filter((item) => item.confirmed).length} hypotheses)`}
                        </button>
                    </div>
                </form>
            </section>
            {initialCycles.length === 0 ? (
                <p className="rounded-xl border border-dashed border-slate-700 p-12 text-center text-slate-400">
                    No planning cycles yet.
                </p>
            ) : (
                <section aria-labelledby="planning-cycles-heading">
                    <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
                        <div>
                            <h2
                                id="planning-cycles-heading"
                                className="text-lg font-semibold"
                            >
                                Planning cycles
                            </h2>
                            <p className="mt-1 text-sm text-slate-400">
                                Select one cycle to review its simulation,
                                plans, and decision history.
                            </p>
                        </div>
                        <label className="grid w-full gap-1 text-xs text-slate-400 lg:hidden">
                            Selected cycle
                            <select
                                value={effectiveSelectedCycleId ?? ""}
                                onChange={(event) =>
                                    setSelectedCycleId(event.target.value)
                                }
                                className={inputClass}
                            >
                                {initialCycles.map((cycle) => (
                                    <option key={cycle.id} value={cycle.id}>
                                        {cycle.scenario.name} —{" "}
                                        {humanize(cycle.status)}
                                    </option>
                                ))}
                            </select>
                        </label>
                    </div>
                    <div className="grid items-start gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
                        <nav
                            aria-label="Planning cycles"
                            className="sticky top-4 hidden max-h-[calc(100vh-2rem)] space-y-2 overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900 p-3 lg:block"
                        >
                            {initialCycles.map((cycle) => {
                                const selected =
                                    cycle.id === effectiveSelectedCycleId;
                                return (
                                    <button
                                        key={cycle.id}
                                        type="button"
                                        aria-current={
                                            selected ? "true" : undefined
                                        }
                                        onClick={() =>
                                            setSelectedCycleId(cycle.id)
                                        }
                                        className={`w-full rounded-xl border p-3 text-left transition ${
                                            selected
                                                ? "border-sky-700 bg-sky-950/60"
                                                : "border-slate-800 bg-slate-950 hover:border-slate-700"
                                        }`}
                                    >
                                        <span className="flex items-start justify-between gap-2">
                                            <span className="line-clamp-2 text-sm font-medium text-slate-100">
                                                {cycle.scenario.name}
                                            </span>
                                            <StatusBadge
                                                status={cycle.status}
                                            />
                                        </span>
                                        <span className="mt-2 block text-xs text-slate-400">
                                            {Math.round(
                                                cycle.scenario
                                                    .occurrence_probability *
                                                    100,
                                            )}
                                            % risk ·{" "}
                                            {cycle.scenario.disruptions.length}{" "}
                                            disruption
                                            {cycle.scenario.disruptions
                                                .length === 1
                                                ? ""
                                                : "s"}
                                        </span>
                                        <span className="mt-1 block truncate font-mono text-[10px] text-slate-600">
                                            {cycle.id}
                                        </span>
                                        {cycle.error_message && (
                                            <span className="mt-2 block text-xs text-amber-300">
                                                Requires attention
                                            </span>
                                        )}
                                    </button>
                                );
                            })}
                        </nav>
                        <div className="min-w-0">
                            {selectedCycle && (
                                <CycleCard
                                    key={`${selectedCycle.id}-${selectedCycle.status}-${selectedCycle.plans.length}`}
                                    initialCycle={selectedCycle}
                                />
                            )}
                        </div>
                    </div>
                </section>
            )}
        </div>
    );
}
