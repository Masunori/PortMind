"use client";

import { useState } from "react";

import LoadingButton from "@/components/LoadingButton";
import type { Plan } from "@/types/plan";
import type { RunEvent, RunEventType, RunResponse } from "@/types/run";

const DEMO_SIGNAL = "Severe weather may close Hai Phong for 2–3 days.";
const EVENT_TYPES: RunEventType[] = [
    "RUN_STARTED",
    "SIGNAL_INTERPRETED",
    "ENTITIES_GROUNDED",
    "EXPOSURE_ANALYZED",
    "SCENARIOS_GENERATED",
    "PLANS_GENERATED",
    "SIMULATION_STARTED",
    "SIMULATION_COMPLETED",
    "RANKING_COMPLETED",
    "RUN_COMPLETED",
    "RUN_FAILED",
];

const MILESTONES: Array<{ type: RunEventType; label: string }> = [
    { type: "SIGNAL_INTERPRETED", label: "Signal interpreted" },
    { type: "ENTITIES_GROUNDED", label: "Entities grounded" },
    { type: "EXPOSURE_ANALYZED", label: "Exposure analyzed" },
    { type: "SCENARIOS_GENERATED", label: "Scenarios generated" },
    { type: "PLANS_GENERATED", label: "Plans generated" },
    { type: "RANKING_COMPLETED", label: "Plan ranking completed" },
];

function backendUrl(): string {
    return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

export default function DemoRunPanel() {
    const [run, setRun] = useState<RunResponse | null>(null);
    const [events, setEvents] = useState<RunEvent[]>([]);
    const [busyAction, setBusyAction] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const busy = busyAction !== null;

    async function loadRun(runId: string): Promise<void> {
        const response = await fetch(`${backendUrl()}/api/runs/${runId}`);
        if (!response.ok) {
            throw new Error(`Unable to load run (${response.status})`);
        }
        setRun((await response.json()) as RunResponse);
    }

    function observeRun(runId: string): void {
        const source = new EventSource(`${backendUrl()}/api/runs/${runId}/events`);
        for (const type of EVENT_TYPES) {
            source.addEventListener(type, (message) => {
                const event = JSON.parse((message as MessageEvent<string>).data) as RunEvent;
                setEvents((current) =>
                    current.some((item) => item.sequence === event.sequence)
                        ? current
                        : [...current, event],
                );
                if (type === "RUN_COMPLETED" || type === "RUN_FAILED") {
                    source.close();
                    void loadRun(runId)
                        .catch((caught) => setError(caught instanceof Error ? caught.message : "Run refresh failed"))
                        .finally(() => setBusyAction(null));
                }
            });
        }
        source.onerror = () => {
            source.close();
            setError("Run event stream disconnected");
            setBusyAction(null);
        };
    }

    async function injectDemoSignal(): Promise<void> {
        setBusyAction("inject");
        setError(null);
        setEvents([]);
        setRun(null);
        try {
            const response = await fetch(`${backendUrl()}/api/runs`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ signal: DEMO_SIGNAL }),
            });
            if (!response.ok) {
                throw new Error(`Unable to start demo run (${response.status})`);
            }
            const generated = (await response.json()) as RunResponse;
            setRun(generated);
            observeRun(generated.run_id);
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Demo run failed");
            setBusyAction(null);
        }
    }

    async function resetDemo(): Promise<void> {
        setBusyAction("reset");
        setError(null);
        try {
            const response = await fetch(`${backendUrl()}/api/demo/reset`, {
                method: "POST",
            });
            if (!response.ok) {
                throw new Error(`Unable to reset demo (${response.status})`);
            }
            setRun(null);
            setEvents([]);
            window.location.reload();
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Demo reset failed");
            setBusyAction(null);
        }
    }

    async function decidePlan(plan: Plan, decision: "approve" | "reject"): Promise<void> {
        setBusyAction(`decision:${decision}`);
        setError(null);
        try {
            const response = await fetch(
                `${backendUrl()}/api/plans/${plan.id}/${decision}`,
                { method: "POST" },
            );
            if (!response.ok) {
                setError(`Unable to ${decision} plan (${response.status})`);
                return;
            }
            const updated = (await response.json()) as Plan;
            setRun((current) => current ? {
                ...current,
                plans: current.plans.map((item) => item.id === updated.id ? updated : item),
            } : current);
        } finally {
            setBusyAction(null);
        }
    }

    const eventTypes = new Set(events.map((event) => event.type));
    const simulation = [...events]
        .reverse()
        .find((event) => event.type === "SIMULATION_COMPLETED");
    const recommended = run?.plans.find(
        (plan) => plan.id === run.recommendation?.recommended_plan,
    );

    return (
        <section className="mb-6 rounded-2xl border border-cyan-800 bg-cyan-950/30 p-5 shadow-xl shadow-black/20">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-400">
                        Canonical local demo
                    </p>
                    <h2 className="mt-2 text-lg font-bold text-slate-100">
                        Typhoon response workflow
                    </h2>
                    <p className="mt-1 text-sm text-slate-400">{DEMO_SIGNAL}</p>
                </div>
                <div className="flex gap-3">
                    <LoadingButton
                        type="button"
                        disabled={busy}
                        pending={busyAction === "reset"}
                        pendingLabel="Resetting…"
                        onClick={() => void resetDemo()}
                        className="rounded-xl border border-slate-600 bg-slate-900 px-4 py-3 text-sm font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                    >
                        Reset Demo
                    </LoadingButton>
                    <LoadingButton
                        type="button"
                        disabled={busy}
                        pending={busyAction === "inject"}
                        pendingLabel="Running workflow…"
                        onClick={() => void injectDemoSignal()}
                        className="rounded-xl bg-cyan-700 px-4 py-3 text-sm font-semibold text-white hover:bg-cyan-600 disabled:opacity-50"
                    >
                        Inject Demo Signal
                    </LoadingButton>
                </div>
            </div>

            {error && <p className="mt-4 rounded-lg bg-red-950 p-3 text-sm text-red-300">{error}</p>}

            {(run || events.length > 0) && (
                <div className="mt-5 grid gap-5 border-t border-cyan-900 pt-5 sm:grid-cols-2">
                    <ol className="space-y-2 text-sm">
                        {MILESTONES.map((milestone) => (
                            <li key={milestone.type} className={eventTypes.has(milestone.type) ? "text-emerald-300" : "text-slate-500"}>
                                {eventTypes.has(milestone.type) ? "✓" : "○"} {milestone.label}
                            </li>
                        ))}
                        {simulation && (
                            <li className="text-cyan-300">
                                → Running simulation {String(simulation.payload.completed)} / {String(simulation.payload.total)}
                            </li>
                        )}
                    </ol>

                    <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Recommendation
                        </p>
                        {recommended ? (
                            <div className="mt-2 rounded-xl border border-emerald-800 bg-emerald-950/50 p-4">
                                <p className="font-bold text-emerald-200">{recommended.name} ★</p>
                                <p className="mt-1 text-xs text-emerald-400">{recommended.status}</p>
                                <div className="mt-3 flex gap-2">
                                    <LoadingButton type="button" disabled={busy} pending={busyAction === "decision:approve"} pendingLabel="Approving…" onClick={() => void decidePlan(recommended, "approve")} className="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white">
                                        Approve
                                    </LoadingButton>
                                    <LoadingButton type="button" disabled={busy} pending={busyAction === "decision:reject"} pendingLabel="Rejecting…" onClick={() => void decidePlan(recommended, "reject")} className="rounded-lg bg-red-800 px-3 py-2 text-xs font-semibold text-white">
                                        Reject
                                    </LoadingButton>
                                </div>
                            </div>
                        ) : (
                            <p className="mt-2 text-sm text-slate-500">Pending workflow completion</p>
                        )}
                    </div>
                </div>
            )}
        </section>
    );
}
