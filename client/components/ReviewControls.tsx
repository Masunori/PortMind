"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import type { Evidence } from "@/types/evidence";
import type { Signal } from "@/types/signal";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function evidenceExcerpt(item: Evidence): string {
    const value =
        item.content ??
        item.content_reference ??
        (item.structured_content
            ? JSON.stringify(item.structured_content)
            : "");
    const compact = value.replace(/\s+/g, " ").trim();
    return compact.length > 180 ? `${compact.slice(0, 177)}…` : compact;
}

export default function ReviewControls({
    signals,
    evidence,
}: {
    signals: Signal[];
    evidence: Evidence[];
}) {
    const router = useRouter();
    const [busy, setBusy] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [, startTransition] = useTransition();

    async function decide(signal: Signal, decision: "ACCEPTED" | "REJECTED") {
        setBusy(signal.signal_id);
        setError(null);
        try {
            const response = await fetch(
                `${apiUrl}/api/signals/${signal.signal_id}/review`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ decision }),
                },
            );
            if (!response.ok) {
                const body = (await response.json().catch(() => null)) as {
                    detail?: string;
                } | null;
                throw new Error(
                    body?.detail ?? `Review failed (${response.status})`,
                );
            }
            startTransition(() => router.refresh());
        } catch (caught) {
            setError(
                caught instanceof Error ? caught.message : "Review failed",
            );
        } finally {
            setBusy(null);
        }
    }

    return (
        <div className="space-y-4">
            {error && (
                <p
                    role="alert"
                    className="rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-300"
                >
                    {error}
                </p>
            )}
            {signals.length === 0 ? (
                <p className="rounded-xl border border-dashed border-slate-700 p-10 text-center text-slate-400">
                    No signals are waiting for review.
                </p>
            ) : (
                signals.map((signal) => {
                    const canAccept =
                        signal.processing_state === "READY_FOR_REVIEW";
                    const linkedEvidence = signal.evidence_ids.map((id) =>
                        evidence.find((item) => item.id === id),
                    );
                    return (
                        <article
                            key={signal.id}
                            className="rounded-xl border border-slate-800 bg-slate-900 p-5"
                        >
                            <div className="flex flex-wrap items-start justify-between gap-4">
                                <div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <h2 className="font-semibold">
                                            {signal.signal_type}
                                        </h2>
                                        <span
                                            className={`rounded-full border px-2 py-1 text-xs ${canAccept ? "border-emerald-800 text-emerald-300" : "border-amber-800 text-amber-300"}`}
                                        >
                                            {signal.processing_state.replaceAll(
                                                "_",
                                                " ",
                                            )}
                                        </span>
                                    </div>
                                    <p className="mt-1 text-sm text-slate-400">
                                        {signal.classification} · severity{" "}
                                        {Math.round(signal.severity * 100)}% ·
                                        probability{" "}
                                        {Math.round(
                                            signal.occurrence_probability * 100,
                                        )}
                                        %
                                    </p>
                                    {signal.retry_of_signal_id && (
                                        <p className="mt-1 text-xs text-violet-300">
                                            Reprocessed from rejected signal{" "}
                                            <span className="font-mono">
                                                {signal.retry_of_signal_id}
                                            </span>
                                        </p>
                                    )}
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        disabled={busy !== null || !canAccept}
                                        title={
                                            !canAccept
                                                ? "Resolve processing issues before accepting"
                                                : undefined
                                        }
                                        onClick={() =>
                                            void decide(signal, "ACCEPTED")
                                        }
                                        className="rounded-lg bg-emerald-700 px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
                                    >
                                        Accept
                                    </button>
                                    <button
                                        disabled={busy !== null}
                                        onClick={() =>
                                            void decide(signal, "REJECTED")
                                        }
                                        className="rounded-lg border border-red-800 px-3 py-2 text-sm text-red-300"
                                    >
                                        Reject
                                    </button>
                                </div>
                            </div>
                            <div className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
                                <div>
                                    <h3 className="text-slate-500">
                                        Supporting evidence
                                    </h3>
                                    {linkedEvidence.length === 0 ? (
                                        <p>None</p>
                                    ) : (
                                        <ul className="mt-1 space-y-2">
                                            {linkedEvidence.map(
                                                (item, index) =>
                                                    item ? (
                                                        <li
                                                            key={item.id}
                                                            className="rounded-lg bg-slate-950 p-3"
                                                        >
                                                            <a
                                                                href={`/evidence${item.archived_at ? "?view=archive" : ""}#${encodeURIComponent(item.id)}`}
                                                                className="font-medium text-sky-300 hover:underline"
                                                            >
                                                                {item.title}
                                                            </a>
                                                            <p className="mt-1 text-xs text-slate-400">
                                                                {evidenceExcerpt(
                                                                    item,
                                                                ) ||
                                                                    "Raw content is unavailable."}
                                                            </p>
                                                            <p className="mt-1 font-mono text-[10px] text-slate-600">
                                                                {item.id}
                                                            </p>
                                                        </li>
                                                    ) : (
                                                        <li
                                                            key={
                                                                signal
                                                                    .evidence_ids[
                                                                    index
                                                                ]
                                                            }
                                                            className="text-slate-400"
                                                        >
                                                            Unavailable evidence{" "}
                                                            <span className="font-mono text-xs">
                                                                {
                                                                    signal
                                                                        .evidence_ids[
                                                                        index
                                                                    ]
                                                                }
                                                            </span>
                                                        </li>
                                                    ),
                                            )}
                                        </ul>
                                    )}
                                </div>
                                <div>
                                    <h3 className="text-slate-500">
                                        Target entities
                                    </h3>
                                    <p className="mt-1">
                                        {signal.entities
                                            .filter(
                                                (entity) => entity.is_target,
                                            )
                                            .map(
                                                (entity) =>
                                                    `${entity.mention} (${entity.status})`,
                                            )
                                            .join(", ") || "None"}
                                    </p>
                                    <h3 className="mt-3 text-slate-500">
                                        Related entities
                                    </h3>
                                    <p className="mt-1">
                                        {signal.entities
                                            .filter(
                                                (entity) => !entity.is_target,
                                            )
                                            .map(
                                                (entity) =>
                                                    `${entity.mention} (${entity.status})`,
                                            )
                                            .join(", ") || "None"}
                                    </p>
                                </div>
                            </div>
                            {signal.mapping_errors.length > 0 && (
                                <div className="mt-4 rounded-lg border border-amber-900 bg-amber-950/50 p-3 text-sm text-amber-300">
                                    <p className="font-medium">
                                        Needs attention
                                    </p>
                                    <ul className="mt-1 list-disc pl-5">
                                        {signal.mapping_errors.map(
                                            (message) => (
                                                <li key={message}>{message}</li>
                                            ),
                                        )}
                                    </ul>
                                </div>
                            )}
                            <details className="mt-4">
                                <summary className="cursor-pointer text-sm text-sky-300">
                                    Review details
                                </summary>
                                <pre className="mt-3 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-300">
                                    {JSON.stringify(
                                        signal.normalized_disruption,
                                        null,
                                        2,
                                    )}
                                </pre>
                            </details>
                        </article>
                    );
                })
            )}
        </div>
    );
}
