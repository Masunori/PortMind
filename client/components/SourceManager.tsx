"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState, useTransition } from "react";

import LoadingButton from "@/components/LoadingButton";
import type { DataSource, DocumentReviewItem } from "@/types/source";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const singaporeOffsetMilliseconds = 8 * 60 * 60 * 1000;

function formatSingaporeTimestamp(value: string): string {
    const timestamp = new Date(value);
    if (Number.isNaN(timestamp.getTime())) {
        return "invalid timestamp";
    }
    return `${new Date(timestamp.getTime() + singaporeOffsetMilliseconds)
        .toISOString()
        .slice(0, 19)
        .replace("T", " ")} SGT`;
}

interface SourceManagerProps {
    initialSources: DataSource[];
    documentItems: DocumentReviewItem[];
}

export default function SourceManager({
    initialSources,
    documentItems,
}: SourceManagerProps) {
    const router = useRouter();
    const [error, setError] = useState<string | null>(null);
    const [busyAction, setBusyAction] = useState<string | null>(null);
    const [lastAction, setLastAction] = useState<string | null>(null);
    const [isPending, startTransition] = useTransition();
    const controlsDisabled = busyAction !== null || isPending;

    function actionPending(action: string): boolean {
        return busyAction === action || (isPending && lastAction === action);
    }

    async function request(
        action: string,
        path: string,
        init: RequestInit,
    ): Promise<void> {
        setError(null);
        setBusyAction(action);
        setLastAction(action);
        try {
            const response = await fetch(`${apiUrl}${path}`, init);
            if (!response.ok) {
                const detail = (await response.json().catch(() => null)) as
                    | { detail?: string }
                    | null;
                throw new Error(detail?.detail ?? `Request failed (${response.status})`);
            }
            startTransition(() => router.refresh());
        } finally {
            setBusyAction(null);
        }
    }

    async function createWebsite(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        try {
            await request("create-source", "/api/sources", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: form.get("name"),
                    type: "WEBSITE",
                    description: form.get("description"),
                    url: form.get("url"),
                    scrape_interval_minutes: Number(form.get("interval")),
                    scraper_type: "HTML",
                    scraper_config_json: {
                        enabled: true,
                        mode: form.get("discovery_mode"),
                        max_depth: Number(form.get("max_depth")),
                        max_pages: Number(form.get("max_pages")),
                        keywords: String(form.get("keywords"))
                            .split(",")
                            .map((item) => item.trim())
                            .filter(Boolean),
                        allowed_paths: String(form.get("allowed_paths"))
                            .split(",")
                            .map((item) => item.trim())
                            .filter(Boolean),
                        excluded_paths: String(form.get("excluded_paths"))
                            .split(",")
                            .map((item) => item.trim())
                            .filter(Boolean),
                        feed_url: form.get("feed_url") || null,
                        sitemap_url: form.get("sitemap_url") || null,
                    },
                }),
            });
            event.currentTarget.reset();
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Could not add source");
        }
    }

    async function updateWebsite(source: DataSource, form: FormData) {
        try {
            await request(`edit:${source.id}`, `/api/sources/${source.id}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: form.get("name"),
                    description: form.get("description"),
                    url: form.get("url"),
                    scrape_interval_minutes: Number(form.get("interval")),
                    scraper_type: "HTML",
                    scraper_config_json: {
                        enabled: form.get("discovery_enabled") === "on",
                        mode: form.get("discovery_mode"),
                        max_depth: Number(form.get("max_depth")),
                        max_pages: Number(form.get("max_pages")),
                        keywords: String(form.get("keywords"))
                            .split(",")
                            .map((item) => item.trim())
                            .filter(Boolean),
                        allowed_paths: String(form.get("allowed_paths"))
                            .split(",")
                            .map((item) => item.trim())
                            .filter(Boolean),
                        excluded_paths: String(form.get("excluded_paths"))
                            .split(",")
                            .map((item) => item.trim())
                            .filter(Boolean),
                        feed_url: String(form.get("feed_url") || "") || null,
                        sitemap_url: String(form.get("sitemap_url") || "") || null,
                    },
                }),
            });
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Could not update source");
        }
    }

    async function removeSource(source: DataSource) {
        const confirmed = window.confirm(
            `Delete “${source.name}”? Its collected documents and review records will also be deleted. This cannot be undone.`,
        );
        if (!confirmed) {
            return;
        }
        try {
            await request(`delete:${source.id}`, `/api/sources/${source.id}`, {
                method: "DELETE",
            });
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Could not delete source");
        }
    }

    async function toggle(source: DataSource) {
        try {
            await request(`toggle:${source.id}`, `/api/sources/${source.id}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enabled: !source.enabled }),
            });
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Could not update source");
        }
    }

    async function collect(source: DataSource) {
        try {
            await request(
                `collect:${source.id}`,
                `/api/sources/${source.id}/collect`,
                { method: "POST" },
            );
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Collection failed");
        }
    }

    async function upload(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        try {
            await request("upload", "/api/documents/upload", {
                method: "POST",
                body: form,
            });
            event.currentTarget.reset();
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Upload failed");
        }
    }

    async function assessDocument(documentId: string) {
        try {
            await request(
                `assess:${documentId}`,
                `/api/documents/${documentId}/assess`,
                { method: "POST" },
            );
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Assessment failed");
        }
    }

    async function overrideDocument(documentId: string, decision: "RELEVANT" | "IRRELEVANT") {
        try {
            await request(`override:${documentId}:${decision}`, `/api/documents/${documentId}/assessment`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ decision }),
            });
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Override failed");
        }
    }

    async function extractCandidate(documentId: string) {
        try {
            await request(`extract:${documentId}`, `/api/disruption-candidates/from-document/${documentId}`, {
                method: "POST",
            });
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Extraction failed");
        }
    }

    return (
        <div className="grid gap-6 xl:grid-cols-[minmax(360px,0.7fr)_minmax(0,1.3fr)]">
            <div className="space-y-6">
                <form onSubmit={createWebsite} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                    <h2 className="text-lg font-semibold">Add website source</h2>
                    <div className="mt-4 grid gap-3">
                        <input required name="name" placeholder="Source name" className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" />
                        <input required name="url" type="url" placeholder="https://…" className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" />
                        <textarea name="description" placeholder="What this source covers" className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" />
                        <label className="text-sm text-slate-400">
                            Collection interval (minutes)
                            <input required min="1" defaultValue="30" name="interval" type="number" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" />
                        </label>
                        <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                            <h3 className="text-sm font-semibold text-slate-200">Article discovery</h3>
                            <p className="mt-1 text-xs leading-5 text-slate-500">
                                Auto checks RSS/Atom and sitemaps, then performs a bounded same-site breadth-first crawl.
                            </p>
                            <div className="mt-3 grid gap-3 sm:grid-cols-2">
                                <label className="text-xs text-slate-400">
                                    Discovery mode
                                    <select name="discovery_mode" defaultValue="AUTO" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100">
                                        <option value="AUTO">Auto</option>
                                        <option value="RSS">RSS/Atom only</option>
                                        <option value="SITEMAP">Sitemap only</option>
                                        <option value="PAGE">Page links only</option>
                                    </select>
                                </label>
                                <label className="text-xs text-slate-400">
                                    Maximum link depth
                                    <input name="max_depth" type="number" min="0" max="5" defaultValue="2" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100" />
                                </label>
                                <label className="text-xs text-slate-400">
                                    Maximum pages per run
                                    <input name="max_pages" type="number" min="1" max="500" defaultValue="50" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100" />
                                </label>
                                <label className="text-xs text-slate-400">
                                    Keywords, comma-separated
                                    <input name="keywords" defaultValue="port, closure, congestion, typhoon, disruption" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100" />
                                </label>
                            </div>
                            <input name="feed_url" type="url" placeholder="Optional RSS/Atom URL" className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm" />
                            <input name="sitemap_url" type="url" placeholder="Optional sitemap URL" className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm" />
                            <input name="allowed_paths" placeholder="Allowed paths, e.g. /news/, /alerts/" className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm" />
                            <input name="excluded_paths" defaultValue="/careers/, /login/, /search/" placeholder="Excluded paths" className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm" />
                        </div>
                        <LoadingButton disabled={controlsDisabled} pending={actionPending("create-source")} pendingLabel="Adding source…" className="rounded-lg bg-sky-600 px-4 py-2 font-semibold hover:bg-sky-500">Add source</LoadingButton>
                    </div>
                </form>
                <form onSubmit={upload} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                    <h2 className="text-lg font-semibold">Upload intelligence</h2>
                    <p className="mt-1 text-sm text-slate-400">TXT, PDF, or DOCX · maximum 10 MB</p>
                    <input required name="file" type="file" accept=".txt,.pdf,.docx" className="mt-4 block w-full text-sm text-slate-300" />
                    <LoadingButton disabled={controlsDisabled} pending={actionPending("upload")} pendingLabel="Uploading…" className="mt-4 w-full rounded-lg bg-sky-600 px-4 py-2 font-semibold hover:bg-sky-500">Upload</LoadingButton>
                </form>
                {error && <p className="rounded-lg border border-red-800 bg-red-950/50 p-3 text-sm text-red-300">{error}</p>}
            </div>
            <div className="space-y-6">
                <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                    <h2 className="text-lg font-semibold">Configured sources</h2>
                    <div className="mt-4 space-y-3">
                        {initialSources.length === 0 && <p className="text-sm text-slate-500">No sources configured.</p>}
                        {initialSources.map((source) => (
                            <article key={source.id} className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div>
                                        <h3 className="font-semibold">{source.name}</h3>
                                        <p className="mt-1 break-all text-sm text-slate-400">{source.url ?? "Uploaded documents"}</p>
                                    </div>
                                    <span className={`rounded-full px-2 py-1 text-xs font-bold ${source.last_status === "FAILED" ? "bg-red-950 text-red-300" : source.last_status === "HEALTHY" ? "bg-emerald-950 text-emerald-300" : "bg-slate-800 text-slate-400"}`}>{source.last_status}</span>
                                </div>
                                <p className="mt-3 text-xs text-slate-500">Last: {source.last_run_at ? formatSingaporeTimestamp(source.last_run_at) : "never"} · Next: {source.next_run_at ? formatSingaporeTimestamp(source.next_run_at) : "not scheduled"}</p>
                                {source.last_error && <p className="mt-2 text-sm text-red-300">{source.last_error}</p>}
                                {source.type === "WEBSITE" && (
                                    <details className="mt-3 rounded-lg border border-slate-800 p-3">
                                        <summary className="cursor-pointer text-sm text-slate-300">Edit source and discovery settings</summary>
                                        <form action={(form) => updateWebsite(source, form)} className="mt-3 grid gap-2 sm:grid-cols-2">
                                            <label className="text-xs text-slate-400">Source name<input required name="name" defaultValue={source.name} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100" /></label>
                                            <label className="text-xs text-slate-400">Collection interval (minutes)<input required name="interval" type="number" min="1" defaultValue={source.scrape_interval_minutes ?? 30} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100" /></label>
                                            <label className="text-xs text-slate-400 sm:col-span-2">Website URL<input required name="url" type="url" defaultValue={source.url ?? ""} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100" /></label>
                                            <label className="text-xs text-slate-400 sm:col-span-2">Description<textarea name="description" defaultValue={source.description} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100" /></label>
                                            <label className="flex items-center gap-2 text-xs text-slate-400">
                                                <input name="discovery_enabled" type="checkbox" defaultChecked={source.scraper_config_json?.enabled ?? false} />
                                                Discover article pages
                                            </label>
                                            <select name="discovery_mode" defaultValue={source.scraper_config_json?.mode ?? "AUTO"} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm">
                                                <option value="AUTO">Auto</option>
                                                <option value="RSS">RSS/Atom only</option>
                                                <option value="SITEMAP">Sitemap only</option>
                                                <option value="PAGE">Page links only</option>
                                            </select>
                                            <label className="text-xs text-slate-400">Depth<input name="max_depth" type="number" min="0" max="5" defaultValue={source.scraper_config_json?.max_depth ?? 2} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100" /></label>
                                            <label className="text-xs text-slate-400">Page budget<input name="max_pages" type="number" min="1" max="500" defaultValue={source.scraper_config_json?.max_pages ?? 50} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100" /></label>
                                            <input name="keywords" defaultValue={source.scraper_config_json?.keywords?.join(", ") ?? ""} placeholder="Keywords" className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm sm:col-span-2" />
                                            <input name="feed_url" type="url" defaultValue={source.scraper_config_json?.feed_url ?? ""} placeholder="Optional RSS/Atom URL" className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm sm:col-span-2" />
                                            <input name="sitemap_url" type="url" defaultValue={source.scraper_config_json?.sitemap_url ?? ""} placeholder="Optional sitemap URL" className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm sm:col-span-2" />
                                            <input name="allowed_paths" defaultValue={source.scraper_config_json?.allowed_paths?.join(", ") ?? ""} placeholder="Allowed paths" className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm sm:col-span-2" />
                                            <input name="excluded_paths" defaultValue={source.scraper_config_json?.excluded_paths?.join(", ") ?? ""} placeholder="Excluded paths" className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm sm:col-span-2" />
                                            <LoadingButton disabled={controlsDisabled} pending={actionPending(`edit:${source.id}`)} pendingLabel="Saving source…" className="rounded-md border border-sky-700 px-3 py-1.5 text-sm text-sky-300 sm:col-span-2">Save all settings</LoadingButton>
                                        </form>
                                    </details>
                                )}
                                <div className="mt-3 flex gap-2">
                                    <LoadingButton type="button" disabled={controlsDisabled} pending={actionPending(`toggle:${source.id}`)} pendingLabel="Updating…" onClick={() => toggle(source)} className="rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800">{source.enabled ? "Disable" : "Enable"}</LoadingButton>
                                    {source.type === "WEBSITE" && <LoadingButton type="button" disabled={controlsDisabled} pending={actionPending(`collect:${source.id}`)} pendingLabel="Collecting…" onClick={() => collect(source)} className="rounded-md border border-sky-700 px-3 py-1.5 text-sm text-sky-300 hover:bg-sky-950">Collect now</LoadingButton>}
                                    <LoadingButton type="button" disabled={controlsDisabled} pending={actionPending(`delete:${source.id}`)} pendingLabel="Deleting…" onClick={() => removeSource(source)} className="rounded-md border border-red-800 px-3 py-1.5 text-sm text-red-300 hover:bg-red-950">Delete</LoadingButton>
                                </div>
                            </article>
                        ))}
                    </div>
                </section>
                <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                    <h2 className="text-lg font-semibold">Raw documents</h2>
                    <div className="mt-4 space-y-3">
                        {documentItems.length === 0 && <p className="text-sm text-slate-500">No documents collected yet.</p>}
                        {documentItems.map(({ document, assessment }) => (
                            <details key={document.id} className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                                <summary className="cursor-pointer font-medium">{document.title} <span className="ml-2 text-xs text-slate-500">{formatSingaporeTimestamp(document.collected_at)}</span></summary>
                                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-300">{document.content}</p>
                                <p className="mt-3 font-mono text-xs text-slate-600">SHA-256 {document.content_hash}</p>
                                {assessment && (
                                    <div className="mt-3 rounded-lg border border-slate-800 p-3 text-sm">
                                        <p><span className="font-semibold text-sky-300">{assessment.effective_decision}</span> · {Math.round(assessment.relevance_probability * 100)}%</p>
                                        <p className="mt-1 text-slate-400">{assessment.rationale}</p>
                                        {assessment.human_override && <p className="mt-1 text-xs text-amber-300">Human override: {assessment.human_override}</p>}
                                    </div>
                                )}
                                <div className="mt-3 flex flex-wrap gap-2">
                                    <LoadingButton type="button" disabled={controlsDisabled} pending={actionPending(`assess:${document.id}`)} pendingLabel="Assessing…" onClick={() => assessDocument(document.id)} className="rounded-md border border-sky-700 px-3 py-1.5 text-sm text-sky-300 hover:bg-sky-950">Assess relevance</LoadingButton>
                                    {assessment && <LoadingButton type="button" disabled={controlsDisabled} pending={actionPending(`override:${document.id}:RELEVANT`)} pendingLabel="Saving…" onClick={() => overrideDocument(document.id, "RELEVANT")} className="rounded-md border border-emerald-800 px-3 py-1.5 text-sm text-emerald-300 hover:bg-emerald-950">Mark relevant</LoadingButton>}
                                    {assessment && <LoadingButton type="button" disabled={controlsDisabled} pending={actionPending(`override:${document.id}:IRRELEVANT`)} pendingLabel="Saving…" onClick={() => overrideDocument(document.id, "IRRELEVANT")} className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800">Mark irrelevant</LoadingButton>}
                                    {assessment?.effective_decision === "RELEVANT" && <LoadingButton type="button" disabled={controlsDisabled} pending={actionPending(`extract:${document.id}`)} pendingLabel="Extracting…" onClick={() => extractCandidate(document.id)} className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-semibold hover:bg-sky-500">Extract candidate</LoadingButton>}
                                </div>
                            </details>
                        ))}
                    </div>
                </section>
            </div>
        </div>
    );
}
