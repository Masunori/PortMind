"use client";

import { FormEvent, useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import type {
    DeletionImpact,
    DuplicateDeletionPreview,
    DuplicateDeletionResult,
    Evidence,
    EvidenceProcessingEligibility,
} from "@/types/evidence";
import type { DataSource } from "@/types/source";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const evidenceDateFormatter = new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Singapore",
});

export default function EvidenceControls({
    evidence,
    sources,
    archived,
}: {
    evidence: Evidence[];
    sources: DataSource[];
    archived: boolean;
}) {
    const router = useRouter();
    const [busy, setBusy] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [deletionState, setDeletionState] = useState<
        Record<
            string,
            {
                impact: DeletionImpact;
                duplicates: DuplicateDeletionPreview | null;
                processing: EvidenceProcessingEligibility | null;
            }
        >
    >({});
    const [, startTransition] = useTransition();
    const input =
        "rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm";
    useEffect(() => {
        let active = true;
        void Promise.all(
            evidence.map(async (item) => {
                const impactResponse = await fetch(
                    `${apiUrl}/api/evidence/${item.id}/deletion-impact`,
                );
                if (!impactResponse.ok) return null;
                const impact = (await impactResponse.json()) as DeletionImpact;
                let duplicates: DuplicateDeletionPreview | null = null;
                let processing: EvidenceProcessingEligibility | null = null;
                if (!item.duplicate_of_id) {
                    const [duplicateResponse, processingResponse] =
                        await Promise.all([
                            fetch(
                                `${apiUrl}/api/evidence/${item.id}/duplicates/deletion-impact`,
                            ),
                            fetch(
                                `${apiUrl}/api/evidence/${item.id}/processing-eligibility`,
                            ),
                        ]);
                    if (duplicateResponse.ok) {
                        duplicates =
                            (await duplicateResponse.json()) as DuplicateDeletionPreview;
                    }
                    if (processingResponse.ok) {
                        processing =
                            (await processingResponse.json()) as EvidenceProcessingEligibility;
                    }
                }
                return [item.id, { impact, duplicates, processing }] as const;
            }),
        ).then((entries) => {
            if (active) {
                setDeletionState(
                    Object.fromEntries(
                        entries.filter(
                            (entry): entry is NonNullable<typeof entry> =>
                                entry !== null,
                        ),
                    ),
                );
            }
        });
        return () => {
            active = false;
        };
    }, [evidence]);

    function deleteTitle(item: Evidence): string {
        const state = deletionState[item.id];
        if (!state) return "Checking deletion eligibility";
        if (state.impact.can_delete_permanently)
            return "Permanently delete this evidence";
        if (state.impact.protected_by.includes("duplicate_evidence"))
            return "Disabled because duplicate records reference this evidence";
        if (state.impact.protected_by.includes("signal_versions"))
            return "Disabled because signal history references this evidence";
        if (state.impact.protected_by.includes("legal_hold"))
            return "Disabled because this evidence is on legal hold";
        return "Permanent deletion is audit-protected";
    }

    function duplicateCleanup(item: Evidence) {
        const preview = deletionState[item.id]?.duplicates;
        const eligible =
            preview?.candidates.filter((candidate) => candidate.can_delete)
                .length ?? 0;
        return {
            loaded: preview !== undefined && preview !== null,
            total: preview?.candidates.length ?? 0,
            eligible,
        };
    }

    function processingTitle(item: Evidence): string {
        const eligibility = deletionState[item.id]?.processing;
        if (!eligibility) return "Checking processing eligibility";
        if (eligibility.can_process && eligibility.attempts.length > 0)
            return "Create a new candidate linked to the latest rejected signal";
        if (eligibility.can_process)
            return "Process this stored evidence without scraping again";
        if (eligibility.blocked_by.includes("signal_accepted"))
            return "An accepted signal already references this evidence";
        return "A signal from this evidence is still awaiting review";
    }
    async function request(action: string, path: string, init: RequestInit) {
        setBusy(action);
        setError(null);
        setNotice(null);
        try {
            const response = await fetch(`${apiUrl}${path}`, init);
            if (!response.ok) {
                const body = (await response.json().catch(() => null)) as {
                    detail?: string;
                } | null;
                throw new Error(
                    typeof body?.detail === "string"
                        ? body.detail
                        : `Request failed (${response.status})`,
                );
            }
            setNotice("Saved.");
            startTransition(() => router.refresh());
        } catch (caught) {
            setError(
                caught instanceof Error ? caught.message : "Request failed",
            );
        } finally {
            setBusy(null);
        }
    }
    async function remove(item: Evidence) {
        setBusy(`delete-${item.id}`);
        setError(null);
        setNotice(null);
        try {
            const preview = await fetch(
                `${apiUrl}/api/evidence/${item.id}/deletion-impact`,
            );
            if (!preview.ok)
                throw new Error(`Deletion preview failed (${preview.status})`);
            const impact = (await preview.json()) as DeletionImpact;
            if (!impact.can_delete_permanently) {
                const reasons = impact.protected_by.map((reason) =>
                    reason === "duplicate_evidence"
                        ? "duplicate evidence depends on this original; enable Include duplicates and remove those records first"
                        : reason === "signal_versions"
                          ? "accepted or pending signal history references this evidence"
                          : reason === "legal_hold"
                            ? "the evidence is on legal hold"
                            : reason,
                );
                throw new Error(
                    `Permanent deletion is blocked: ${reasons.join("; ")}. Archive or remove raw content instead.`,
                );
            }
            if (!window.confirm(`Permanently delete ${item.title}?`)) return;
            const response = await fetch(`${apiUrl}/api/evidence/${item.id}`, {
                method: "DELETE",
            });
            if (!response.ok) {
                const body = (await response.json().catch(() => null)) as {
                    detail?: string;
                } | null;
                throw new Error(
                    body?.detail ?? `Delete failed (${response.status})`,
                );
            }
            setNotice("Evidence permanently deleted.");
            startTransition(() => router.refresh());
        } catch (caught) {
            setError(
                caught instanceof Error ? caught.message : "Delete failed",
            );
        } finally {
            setBusy(null);
        }
    }
    async function cleanupDuplicates(item: Evidence) {
        setBusy(`duplicates-${item.id}`);
        setError(null);
        setNotice(null);
        try {
            const previewResponse = await fetch(
                `${apiUrl}/api/evidence/${item.id}/duplicates/deletion-impact`,
            );
            if (!previewResponse.ok)
                throw new Error(
                    `Duplicate preview failed (${previewResponse.status})`,
                );
            const preview =
                (await previewResponse.json()) as DuplicateDeletionPreview;
            const eligible = preview.candidates.filter(
                (candidate) => candidate.can_delete,
            );
            const protectedCount = preview.candidates.length - eligible.length;
            if (!preview.candidates.length) {
                setNotice("No duplicate records reference this evidence.");
                return;
            }
            if (!eligible.length)
                throw new Error(
                    `All ${protectedCount} duplicate records are audit-protected and were left unchanged.`,
                );
            if (
                !window.confirm(
                    `Permanently delete ${eligible.length} unprotected duplicate record${eligible.length === 1 ? "" : "s"}? ${protectedCount} protected duplicate${protectedCount === 1 ? "" : "s"} will be skipped.`,
                )
            )
                return;
            const response = await fetch(
                `${apiUrl}/api/evidence/${item.id}/duplicates`,
                { method: "DELETE" },
            );
            const result = (await response.json().catch(() => null)) as
                | DuplicateDeletionResult
                | { detail?: string }
                | null;
            if (!response.ok)
                throw new Error(
                    result && "detail" in result
                        ? String(result.detail)
                        : `Batch delete failed (${response.status})`,
                );
            const completed = result as DuplicateDeletionResult;
            setNotice(
                `Deleted ${completed.deleted_ids.length} duplicate record${completed.deleted_ids.length === 1 ? "" : "s"}; skipped ${completed.skipped.length} protected record${completed.skipped.length === 1 ? "" : "s"}.`,
            );
            startTransition(() => router.refresh());
        } catch (caught) {
            setError(
                caught instanceof Error
                    ? caught.message
                    : "Batch duplicate cleanup failed",
            );
        } finally {
            setBusy(null);
        }
    }
    async function createManual(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const reference = String(form.get("reference") ?? "").trim();
        const content = String(form.get("content") ?? "").trim();
        await request("manual", "/api/evidence", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                source_id: form.get("source_id"),
                kind: "MANUAL",
                title: form.get("title"),
                media_type: "text/plain",
                content: content || null,
                content_reference: reference || null,
                source_url: form.get("source_url") || null,
            }),
        });
    }
    async function upload(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        await request("upload", "/api/evidence/upload", {
            method: "POST",
            body: new FormData(event.currentTarget),
        });
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
            {notice && (
                <p className="rounded-lg border border-emerald-800 bg-emerald-950 p-3 text-sm text-emerald-300">
                    {notice}
                </p>
            )}
            {!archived && (
                <section className="grid gap-5 lg:grid-cols-2">
                    <form
                        onSubmit={upload}
                        className="grid content-start gap-3 rounded-xl border border-slate-800 bg-slate-900 p-5"
                    >
                        <div>
                            <h2 className="font-semibold">Upload evidence</h2>
                            <p className="mt-1 text-sm text-slate-400">
                                Attach a document to an existing source.
                            </p>
                        </div>
                        <select required name="source_id" className={input}>
                            <option value="">Choose source</option>
                            {sources.map((source) => (
                                <option key={source.id} value={source.id}>
                                    {source.name}
                                </option>
                            ))}
                        </select>
                        <label className="group flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed border-slate-600 bg-slate-950/60 px-5 py-7 text-center transition hover:border-sky-500 hover:bg-sky-950/40 focus-within:border-sky-400 focus-within:ring-2 focus-within:ring-sky-400/40">
                            <input
                                required
                                type="file"
                                name="file"
                                accept=".txt,.pdf,.docx,text/plain,application/pdf"
                                className="sr-only"
                                onChange={(event) =>
                                    setSelectedFile(
                                        event.currentTarget.files?.[0] ?? null,
                                    )
                                }
                            />
                            <span
                                className="mb-3 grid size-11 place-items-center rounded-full bg-sky-500/15 text-2xl text-sky-300 transition group-hover:bg-sky-500/25"
                                aria-hidden="true"
                            >
                                ↑
                            </span>
                            <span className="font-semibold text-sky-300">
                                {selectedFile
                                    ? "Choose a different file"
                                    : "Choose a file"}
                            </span>
                            <span className="mt-1 max-w-full truncate text-sm text-slate-300">
                                {selectedFile
                                    ? selectedFile.name
                                    : "Click here to browse your device"}
                            </span>
                            <span className="mt-2 text-xs text-slate-500">
                                TXT, PDF, or DOCX
                            </span>
                        </label>
                        <button
                            disabled={busy !== null}
                            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold"
                        >
                            {busy === "upload"
                                ? "Uploading…"
                                : selectedFile
                                  ? `Upload ${selectedFile.name}`
                                  : "Upload evidence"}
                        </button>
                    </form>
                    <form
                        onSubmit={createManual}
                        className="grid gap-3 rounded-xl border border-slate-800 bg-slate-900 p-5"
                    >
                        <h2 className="font-semibold">
                            Create manual evidence
                        </h2>
                        <select required name="source_id" className={input}>
                            <option value="">Choose source</option>
                            {sources.map((source) => (
                                <option key={source.id} value={source.id}>
                                    {source.name}
                                </option>
                            ))}
                        </select>
                        <input
                            required
                            name="title"
                            placeholder="Title"
                            className={input}
                        />
                        <textarea
                            name="content"
                            placeholder="Content (or provide a reference below)"
                            className={input}
                        />
                        <input
                            name="reference"
                            placeholder="Content reference"
                            className={input}
                        />
                        <input
                            name="source_url"
                            type="url"
                            placeholder="Optional source URL"
                            className={input}
                        />
                        <button
                            disabled={busy !== null}
                            className="rounded-lg bg-slate-700 px-4 py-2 text-sm font-semibold"
                        >
                            Create evidence
                        </button>
                    </form>
                </section>
            )}
            <section className="grid gap-4">
                {evidence.length === 0 ? (
                    <p className="rounded-xl border border-dashed border-slate-700 p-10 text-center text-slate-400">
                        No {archived ? "archived " : ""}evidence.
                    </p>
                ) : (
                    evidence.map((item) => (
                        <article
                            key={item.id}
                            className="rounded-xl border border-slate-800 bg-slate-900 p-5"
                        >
                            <div>
                                <div className="min-w-0">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <h2 className="min-w-0 break-words font-semibold">
                                            {item.title}
                                        </h2>
                                        {item.duplicate_of_id && (
                                            <span className="rounded-full border border-violet-800 bg-violet-950 px-2 py-1 text-[10px] text-violet-300">
                                                Duplicate
                                            </span>
                                        )}
                                    </div>
                                    <p className="mt-1 text-xs text-slate-500">
                                        {item.kind} · {item.source_id} ·{" "}
                                        <time dateTime={item.collected_at}>
                                            {evidenceDateFormatter.format(
                                                new Date(item.collected_at),
                                            )}
                                        </time>
                                    </p>
                                    {item.duplicate_of_id && (
                                        <p className="mt-1 text-xs text-violet-300">
                                            Identical content is retained by{" "}
                                            <span className="font-mono">
                                                {item.duplicate_of_id}
                                            </span>
                                            .
                                        </p>
                                    )}
                                </div>
                                <div className="mt-4 flex flex-wrap gap-2">
                                    {!item.duplicate_of_id && (
                                        <button
                                            disabled={
                                                busy !== null ||
                                                !deletionState[item.id]
                                                    ?.processing?.can_process
                                            }
                                            title={processingTitle(item)}
                                            onClick={() =>
                                                void request(
                                                    `process-${item.id}`,
                                                    `/api/evidence/${item.id}/process`,
                                                    { method: "POST" },
                                                )
                                            }
                                            className="rounded-lg border border-sky-800 px-3 py-2 text-xs text-sky-300 disabled:cursor-not-allowed disabled:opacity-40"
                                        >
                                            {busy === `process-${item.id}`
                                                ? "Processing…"
                                                : deletionState[item.id]
                                                        ?.processing?.attempts
                                                        .length
                                                  ? "Reprocess"
                                                  : "Process / retry"}
                                        </button>
                                    )}
                                    <button
                                        disabled={busy !== null}
                                        onClick={() =>
                                            request(
                                                "archive",
                                                `/api/evidence/${item.id}/${archived ? "restore" : "archive"}`,
                                                { method: "POST" },
                                            )
                                        }
                                        className="rounded-lg border border-slate-700 px-3 py-2 text-xs"
                                    >
                                        {archived ? "Restore" : "Archive"}
                                    </button>
                                    {!item.duplicate_of_id && (
                                        <button
                                            disabled={
                                                busy !== null ||
                                                !duplicateCleanup(item)
                                                    .loaded ||
                                                duplicateCleanup(item)
                                                    .eligible === 0
                                            }
                                            title={
                                                !duplicateCleanup(item).loaded
                                                    ? "Checking duplicate cleanup eligibility"
                                                    : duplicateCleanup(item)
                                                            .total === 0
                                                      ? "No duplicate records reference this evidence"
                                                      : duplicateCleanup(item)
                                                              .eligible === 0
                                                        ? "All duplicate records are audit-protected"
                                                        : `Delete ${duplicateCleanup(item).eligible} unprotected duplicate record${duplicateCleanup(item).eligible === 1 ? "" : "s"}`
                                            }
                                            onClick={() =>
                                                void cleanupDuplicates(item)
                                            }
                                            className="rounded-lg border border-violet-800 px-3 py-2 text-xs text-violet-300 disabled:cursor-not-allowed disabled:opacity-40"
                                        >
                                            {busy === `duplicates-${item.id}`
                                                ? "Checking duplicates…"
                                                : !duplicateCleanup(item).loaded
                                                  ? "Checking duplicates…"
                                                  : duplicateCleanup(item)
                                                          .total === 0
                                                    ? "No duplicates"
                                                    : duplicateCleanup(item)
                                                            .eligible === 0
                                                      ? "Duplicates protected"
                                                      : `Delete ${duplicateCleanup(item).eligible} duplicate${duplicateCleanup(item).eligible === 1 ? "" : "s"}`}
                                        </button>
                                    )}
                                    {!archived && (
                                        <button
                                            disabled={
                                                busy !== null ||
                                                (!item.content &&
                                                    !item.structured_content)
                                            }
                                            onClick={() => {
                                                if (
                                                    window.confirm(
                                                        "Remove raw content while retaining audit metadata?",
                                                    )
                                                )
                                                    void request(
                                                        "redact",
                                                        `/api/evidence/${item.id}/raw-content`,
                                                        { method: "DELETE" },
                                                    );
                                            }}
                                            className="rounded-lg border border-amber-800 px-3 py-2 text-xs text-amber-300"
                                        >
                                            Remove raw content
                                        </button>
                                    )}
                                    <button
                                        disabled={
                                            busy !== null ||
                                            !deletionState[item.id]?.impact
                                                .can_delete_permanently
                                        }
                                        title={deleteTitle(item)}
                                        onClick={() => void remove(item)}
                                        className="rounded-lg border border-red-800 px-3 py-2 text-xs text-red-300 disabled:cursor-not-allowed disabled:opacity-40"
                                    >
                                        {busy === `delete-${item.id}`
                                            ? "Checking…"
                                            : "Delete"}
                                    </button>
                                </div>
                            </div>
                            {(deletionState[item.id]?.processing?.attempts
                                .length ?? 0) > 0 && (
                                <details className="mt-4">
                                    <summary className="cursor-pointer text-sm text-sky-300">
                                        Processing attempts (
                                        {
                                            deletionState[item.id]?.processing
                                                ?.attempts.length
                                        }
                                        )
                                    </summary>
                                    <ol className="mt-3 space-y-2 text-xs text-slate-400">
                                        {deletionState[
                                            item.id
                                        ]?.processing?.attempts.map(
                                            (attempt, index) => (
                                                <li
                                                    key={attempt.signal_id}
                                                    className="rounded-lg bg-slate-950 p-3"
                                                >
                                                    Attempt {index + 1}:{" "}
                                                    <span className="text-slate-200">
                                                        {attempt.signal_type}
                                                    </span>{" "}
                                                    · {attempt.processing_state}{" "}
                                                    · {attempt.review_status}
                                                    {attempt.retry_of_signal_id &&
                                                        " · retry"}
                                                </li>
                                            ),
                                        )}
                                    </ol>
                                </details>
                            )}
                            <details className="mt-4">
                                <summary className="cursor-pointer text-sm text-sky-300">
                                    Evidence content
                                </summary>
                                <p className="mt-3 max-w-3xl whitespace-pre-wrap break-words text-sm text-slate-300">
                                    {item.content ??
                                        item.content_reference ??
                                        JSON.stringify(item.structured_content)}
                                </p>
                            </details>
                            {!archived && (
                                <details className="mt-4">
                                    <summary className="cursor-pointer text-sm text-sky-300">
                                        Edit evidence
                                    </summary>
                                    <form
                                        onSubmit={(event) => {
                                            event.preventDefault();
                                            const form = new FormData(
                                                event.currentTarget,
                                            );
                                            void request(
                                                "edit",
                                                `/api/evidence/${item.id}`,
                                                {
                                                    method: "PATCH",
                                                    headers: {
                                                        "Content-Type":
                                                            "application/json",
                                                    },
                                                    body: JSON.stringify({
                                                        title: form.get(
                                                            "title",
                                                        ),
                                                        content:
                                                            form.get("content"),
                                                        content_reference:
                                                            form.get(
                                                                "reference",
                                                            ) || null,
                                                        source_url:
                                                            form.get(
                                                                "source_url",
                                                            ) || null,
                                                    }),
                                                },
                                            );
                                        }}
                                        className="mt-3 grid gap-2"
                                    >
                                        <input
                                            required
                                            name="title"
                                            defaultValue={item.title}
                                            className={input}
                                        />
                                        <textarea
                                            name="content"
                                            defaultValue={item.content ?? ""}
                                            className={input}
                                        />
                                        <input
                                            name="reference"
                                            defaultValue={
                                                item.content_reference ?? ""
                                            }
                                            placeholder="Content reference"
                                            className={input}
                                        />
                                        <input
                                            name="source_url"
                                            type="url"
                                            defaultValue={item.source_url ?? ""}
                                            placeholder="Source URL"
                                            className={input}
                                        />
                                        <button className="rounded-lg bg-slate-700 px-3 py-2 text-sm">
                                            Save changes
                                        </button>
                                    </form>
                                </details>
                            )}
                        </article>
                    ))
                )}
            </section>
        </div>
    );
}
