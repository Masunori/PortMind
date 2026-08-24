"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import LoadingButton from "@/components/LoadingButton";
import type { CandidateInboxItem } from "@/types/candidate";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function CandidateInbox({ items }: { items: CandidateInboxItem[] }) {
    const router = useRouter();
    const [error, setError] = useState<string | null>(null);
    const [busyAction, setBusyAction] = useState<string | null>(null);
    const [lastAction, setLastAction] = useState<string | null>(null);
    const [isPending, startTransition] = useTransition();
    const controlsDisabled = busyAction !== null || isPending;

    function actionPending(action: string): boolean {
        return busyAction === action || (isPending && lastAction === action);
    }

    async function act(candidateId: string, action: "confirm" | "reject" | "confirm-and-run") {
        const actionKey = `${action}:${candidateId}`;
        setError(null);
        setBusyAction(actionKey);
        setLastAction(actionKey);
        try {
            const response = await fetch(
                `${apiUrl}/api/disruption-candidates/${candidateId}/${action}`,
                { method: "POST" },
            );
            if (!response.ok) {
                const body = (await response.json().catch(() => null)) as { detail?: string } | null;
                setError(body?.detail ?? `${action} failed`);
                return;
            }
            startTransition(() => router.refresh());
        } finally {
            setBusyAction(null);
        }
    }

    async function edit(candidateId: string, form: FormData) {
        const actionKey = `edit:${candidateId}`;
        setError(null);
        setBusyAction(actionKey);
        setLastAction(actionKey);
        try {
            const response = await fetch(`${apiUrl}/api/disruption-candidates/${candidateId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    start_time: Number(form.get("start_time")),
                    end_time: Number(form.get("end_time")),
                    probability: Number(form.get("probability")),
                    severity: Number(form.get("severity")),
                    summary: form.get("summary"),
                }),
            });
            if (!response.ok) {
                const body = (await response.json().catch(() => null)) as { detail?: string } | null;
                setError(body?.detail ?? "Edit failed");
                return;
            }
            startTransition(() => router.refresh());
        } finally {
            setBusyAction(null);
        }
    }

    return (
        <div className="space-y-4">
            {error && <p className="rounded-lg border border-red-800 bg-red-950/50 p-3 text-red-300">{error}</p>}
            {items.length === 0 && <p className="rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center text-slate-500">No potential disruptions. Process a relevant document from Sources.</p>}
            {items.map(({ candidate, exposure }) => (
                <article key={candidate.id} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                        <div>
                            <p className={`text-xs font-bold tracking-widest ${candidate.severity >= 0.8 ? "text-red-400" : "text-amber-400"}`}>{candidate.severity >= 0.8 ? "CRITICAL" : "WARNING"}</p>
                            <h2 className="mt-1 text-xl font-semibold">{candidate.summary}</h2>
                            <p className="mt-2 text-sm text-slate-400">{candidate.disruption_type.replaceAll("_", " ")} · {candidate.affected_locations.join(", ")}</p>
                        </div>
                        <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-semibold">{candidate.review_status}</span>
                    </div>
                    <div className="mt-4 grid gap-3 text-sm sm:grid-cols-4">
                        <p><span className="text-slate-500">Confidence</span><br />{Math.round(candidate.extraction_confidence * 100)}%</p>
                        <p><span className="text-slate-500">Probability</span><br />{Math.round(candidate.probability * 100)}%</p>
                        <p><span className="text-slate-500">Window</span><br />{candidate.start_time}–{candidate.end_time}h</p>
                        <p><span className="text-slate-500">Exposure</span><br />{exposure ? `${exposure.affected_shipments.length} shipments · ${exposure.affected_customers.length} customers` : "Unavailable"}</p>
                    </div>
                    {candidate.validation_errors.length > 0 && <ul className="mt-4 list-disc pl-5 text-sm text-red-300">{candidate.validation_errors.map((item) => <li key={item}>{item}</li>)}</ul>}
                    {candidate.review_status === "PENDING" && (
                        <form action={(form) => edit(candidate.id, form)} className="mt-5 grid gap-3 rounded-xl border border-slate-800 bg-slate-950 p-4 sm:grid-cols-4">
                            <input name="start_time" type="number" min="0" step="0.1" defaultValue={candidate.start_time} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2" aria-label="Start time hours" />
                            <input name="end_time" type="number" min="0" step="0.1" defaultValue={candidate.end_time} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2" aria-label="End time hours" />
                            <input name="probability" type="number" min="0" max="1" step="0.01" defaultValue={candidate.probability} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2" aria-label="Probability" />
                            <input name="severity" type="number" min="0" max="1" step="0.01" defaultValue={candidate.severity} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2" aria-label="Severity" />
                            <textarea name="summary" defaultValue={candidate.summary} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 sm:col-span-3" aria-label="Summary" />
                            <LoadingButton disabled={controlsDisabled} pending={actionPending(`edit:${candidate.id}`)} pendingLabel="Saving…" className="rounded-lg border border-sky-700 px-3 py-2 text-sky-300 hover:bg-sky-950">Save edits</LoadingButton>
                        </form>
                    )}
                    {candidate.review_status === "PENDING" && (
                        <div className="mt-4 flex gap-3">
                            <LoadingButton type="button" disabled={controlsDisabled} pending={actionPending(`reject:${candidate.id}`)} pendingLabel="Rejecting…" onClick={() => act(candidate.id, "reject")} className="rounded-lg border border-red-800 px-4 py-2 text-red-300 hover:bg-red-950">Reject</LoadingButton>
                            <LoadingButton type="button" disabled={candidate.validation_status !== "VALIDATED" || controlsDisabled} pending={actionPending(`confirm:${candidate.id}`)} pendingLabel="Confirming…" onClick={() => act(candidate.id, "confirm")} className="rounded-lg bg-emerald-600 px-4 py-2 font-semibold hover:bg-emerald-500">Confirm disruption</LoadingButton>
                            <LoadingButton type="button" disabled={candidate.validation_status !== "VALIDATED" || controlsDisabled} pending={actionPending(`confirm-and-run:${candidate.id}`)} pendingLabel="Starting analysis…" onClick={() => act(candidate.id, "confirm-and-run")} className="rounded-lg bg-sky-600 px-4 py-2 font-semibold hover:bg-sky-500">Confirm &amp; run analysis</LoadingButton>
                        </div>
                    )}
                    {candidate.run_id && <p className="mt-4 font-mono text-xs text-sky-300">Observable run: {candidate.run_id} · progress available through the existing SSE run stream</p>}
                </article>
            ))}
        </div>
    );
}
