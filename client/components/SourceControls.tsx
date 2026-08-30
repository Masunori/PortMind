"use client";

import { FormEvent, ReactNode, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import type { DataSource, SourceCollectionResult } from "@/types/source";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const input =
    "min-w-0 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm";

function Field({ label, children }: { label: string; children: ReactNode }) {
    return (
        <label className="grid min-w-0 gap-1.5 text-sm">
            <span className="font-medium text-slate-300">{label}</span>
            {children}
        </label>
    );
}

function split(value: FormDataEntryValue | null) {
    return String(value ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function collectionMessage(result: SourceCollectionResult): string {
    const outcomes = [
        [result.processing.ready_for_review, "ready for review"],
        [result.processing.filtered_out, "filtered out"],
        [result.processing.needs_resolution, "needs resolution"],
        [result.processing.mapping_failed, "mapping/validation failed"],
        [result.processing.deferred, "deferred for retry"],
        [result.processing.failed, "unexpectedly failed"],
    ]
        .filter(([count]) => Number(count) > 0)
        .map(([count, label]) => `${count} ${label}`);
    const processing = outcomes.length
        ? ` Processing: ${outcomes.join(", ")}.`
        : "";
    const collectionErrors = result.errors.length
        ? ` Collection warnings: ${result.errors.join("; ")}`
        : "";
    const processingErrors = result.processing.errors.length
        ? ` Processing warnings: ${result.processing.errors
              .map((item) => `${item.evidence_id}: ${item.message}`)
              .join("; ")}`
        : "";

    return `Collection complete: ${result.created_evidence} new, ${result.duplicate_evidence} duplicate.${processing}${collectionErrors}${processingErrors}`;
}

export default function SourceControls({ sources }: { sources: DataSource[] }) {
    const router = useRouter();
    const [busy, setBusy] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<{
        message: string;
        warning: boolean;
    } | null>(null);
    const [, startTransition] = useTransition();

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

            const body = response.status === 204 ? null : await response.json();
            if (action.startsWith("collect:")) {
                const result = body as SourceCollectionResult;
                setNotice({
                    message: collectionMessage(result),
                    warning:
                        result.processing.failed > 0 ||
                        result.processing.deferred > 0 ||
                        result.errors.length > 0,
                });
            } else {
                setNotice({ message: "Saved.", warning: false });
            }
            startTransition(() => router.refresh());
        } catch (caught) {
            setError(
                caught instanceof Error ? caught.message : "Request failed",
            );
        } finally {
            setBusy(null);
        }
    }

    function websitePayload(form: FormData) {
        return {
            name: form.get("name"),
            type: "WEBSITE",
            description: form.get("description"),
            url: form.get("url"),
            enabled: form.get("enabled") === "on",
            scrape_interval_minutes: Number(form.get("interval")),
            scraper_type: "HTML",
            scraper_config_json: {
                enabled: form.get("discovery") === "on",
                mode: form.get("mode"),
                max_depth: Number(form.get("depth")),
                max_pages: Number(form.get("pages")),
                keywords: split(form.get("keywords")),
                allowed_paths: split(form.get("allowed")),
                excluded_paths: split(form.get("excluded")),
                feed_url: form.get("feed") || null,
                sitemap_url: form.get("sitemap") || null,
            },
        };
    }

    async function createWebsite(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        await request("create", "/api/sources", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(
                websitePayload(new FormData(event.currentTarget)),
            ),
        });
    }

    async function createUpload(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        await request("create-upload", "/api/sources", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: form.get("name"),
                type: "UPLOAD",
                description: form.get("description"),
            }),
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
                <div
                    role={notice.warning ? "alert" : "status"}
                    className={`rounded-lg border p-3 text-sm ${
                        notice.warning
                            ? "border-amber-800 bg-amber-950 text-amber-300"
                            : "border-emerald-800 bg-emerald-950 text-emerald-300"
                    }`}
                >
                    <span>{notice.message}</span>
                    {notice.message.includes("ready for review") && (
                        <a
                            href="/review"
                            className="ml-2 font-semibold underline"
                        >
                            Open review queue
                        </a>
                    )}
                </div>
            )}

            <section className="grid gap-5 lg:grid-cols-2">
                <form
                    onSubmit={createWebsite}
                    className="grid gap-3 rounded-xl border border-slate-800 bg-slate-900 p-5"
                >
                    <h2 className="font-semibold">Add website scraper</h2>
                    <Field label="Source name">
                        <input required name="name" className={input} />
                    </Field>
                    <Field label="Website URL">
                        <input
                            required
                            type="url"
                            name="url"
                            placeholder="https://example.com/news"
                            className={input}
                        />
                    </Field>
                    <Field label="Description">
                        <input name="description" className={input} />
                    </Field>
                    <div className="grid gap-3 sm:grid-cols-3">
                        <Field label="Interval (minutes)">
                            <input
                                required
                                min="1"
                                defaultValue="30"
                                type="number"
                                name="interval"
                                className={input}
                            />
                        </Field>
                        <Field label="Collection mode">
                            <select
                                name="mode"
                                defaultValue="AUTO"
                                className={input}
                            >
                                <option>AUTO</option>
                                <option>PAGE</option>
                                <option>RSS</option>
                                <option>SITEMAP</option>
                            </select>
                        </Field>
                        <Field label="Maximum pages">
                            <input
                                min="1"
                                max="500"
                                defaultValue="50"
                                type="number"
                                name="pages"
                                className={input}
                            />
                        </Field>
                    </div>
                    <input type="hidden" name="depth" value="2" />
                    <Field label="Keywords (comma-separated)">
                        <input
                            name="keywords"
                            placeholder="port, disruption, weather"
                            className={input}
                        />
                    </Field>
                    <Field label="Allowed paths (comma-separated)">
                        <input
                            name="allowed"
                            placeholder="/news, /alerts"
                            className={input}
                        />
                    </Field>
                    <Field label="Excluded paths (comma-separated)">
                        <input
                            name="excluded"
                            placeholder="/about, /careers"
                            className={input}
                        />
                    </Field>
                    <Field label="Feed URL (optional)">
                        <input
                            type="url"
                            name="feed"
                            placeholder="https://example.com/feed.xml"
                            className={input}
                        />
                    </Field>
                    <Field label="Sitemap URL (optional)">
                        <input
                            type="url"
                            name="sitemap"
                            placeholder="https://example.com/sitemap.xml"
                            className={input}
                        />
                    </Field>
                    <label className="text-sm">
                        <input type="checkbox" name="enabled" defaultChecked />{" "}
                        Enabled
                    </label>
                    <label className="text-sm">
                        <input
                            type="checkbox"
                            name="discovery"
                            defaultChecked
                        />{" "}
                        Discover linked articles
                    </label>
                    <button
                        disabled={busy !== null}
                        className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold"
                    >
                        Create scraper
                    </button>
                </form>

                <form
                    onSubmit={createUpload}
                    className="grid content-start gap-3 rounded-xl border border-slate-800 bg-slate-900 p-5"
                >
                    <h2 className="font-semibold">Add upload/manual source</h2>
                    <Field label="Source name">
                        <input required name="name" className={input} />
                    </Field>
                    <Field label="Description">
                        <input name="description" className={input} />
                    </Field>
                    <button
                        disabled={busy !== null}
                        className="rounded-lg bg-slate-700 px-4 py-2 text-sm font-semibold"
                    >
                        Create source
                    </button>
                </form>
            </section>

            <section className="grid gap-4">
                {sources.map((source) => (
                    <article
                        key={source.id}
                        className="rounded-xl border border-slate-800 bg-slate-900 p-5"
                    >
                        <div className="flex flex-wrap items-start justify-between gap-4">
                            <div>
                                <h2 className="font-semibold">{source.name}</h2>
                                <p className="text-sm text-slate-400">
                                    {source.url ?? source.type} ·{" "}
                                    {source.last_status}
                                </p>
                                {source.last_error && (
                                    <p className="mt-1 text-xs text-red-300">
                                        {source.last_error}
                                    </p>
                                )}
                            </div>
                            <div className="flex gap-2">
                                {source.type === "WEBSITE" && (
                                    <button
                                        disabled={busy !== null}
                                        aria-busy={
                                            busy === `collect:${source.id}`
                                        }
                                        onClick={() =>
                                            request(
                                                `collect:${source.id}`,
                                                `/api/sources/${source.id}/collect`,
                                                { method: "POST" },
                                            )
                                        }
                                        className="rounded-lg bg-sky-700 px-3 py-2 text-xs disabled:cursor-not-allowed disabled:opacity-60"
                                    >
                                        {busy === `collect:${source.id}`
                                            ? "Collecting…"
                                            : "Collect now"}
                                    </button>
                                )}
                                <button
                                    disabled={busy !== null}
                                    onClick={() =>
                                        request(
                                            "toggle",
                                            `/api/sources/${source.id}`,
                                            {
                                                method: "PATCH",
                                                headers: {
                                                    "Content-Type":
                                                        "application/json",
                                                },
                                                body: JSON.stringify({
                                                    enabled: !source.enabled,
                                                }),
                                            },
                                        )
                                    }
                                    className="rounded-lg border border-slate-700 px-3 py-2 text-xs"
                                >
                                    {source.enabled ? "Disable" : "Enable"}
                                </button>
                                <button
                                    disabled={busy !== null}
                                    onClick={() => {
                                        if (
                                            window.confirm(
                                                `Delete ${source.name}?`,
                                            )
                                        ) {
                                            void request(
                                                "delete",
                                                `/api/sources/${source.id}`,
                                                {
                                                    method: "DELETE",
                                                },
                                            );
                                        }
                                    }}
                                    className="rounded-lg border border-red-800 px-3 py-2 text-xs text-red-300"
                                >
                                    Delete
                                </button>
                            </div>
                        </div>

                        <details className="mt-4">
                            <summary className="cursor-pointer text-sm text-sky-300">
                                Edit source
                            </summary>
                            <form
                                onSubmit={(event) => {
                                    event.preventDefault();
                                    const form = new FormData(
                                        event.currentTarget,
                                    );
                                    const body =
                                        source.type === "WEBSITE"
                                            ? websitePayload(form)
                                            : {
                                                  name: form.get("name"),
                                                  description:
                                                      form.get("description"),
                                                  enabled:
                                                      form.get("enabled") ===
                                                      "on",
                                              };
                                    void request(
                                        "edit",
                                        `/api/sources/${source.id}`,
                                        {
                                            method: "PATCH",
                                            headers: {
                                                "Content-Type":
                                                    "application/json",
                                            },
                                            body: JSON.stringify(body),
                                        },
                                    );
                                }}
                                className="mt-3 grid gap-3 lg:grid-cols-3"
                            >
                                <Field label="Source name">
                                    <input
                                        required
                                        name="name"
                                        defaultValue={source.name}
                                        className={input}
                                    />
                                </Field>
                                <Field label="Description">
                                    <input
                                        name="description"
                                        defaultValue={source.description}
                                        className={input}
                                    />
                                </Field>
                                {source.type === "WEBSITE" && (
                                    <>
                                        <Field label="Website URL">
                                            <input
                                                required
                                                type="url"
                                                name="url"
                                                defaultValue={source.url ?? ""}
                                                className={input}
                                            />
                                        </Field>
                                        <Field label="Interval (minutes)">
                                            <input
                                                name="interval"
                                                type="number"
                                                min="1"
                                                defaultValue={
                                                    source.scrape_interval_minutes ??
                                                    30
                                                }
                                                className={input}
                                            />
                                        </Field>
                                        <Field label="Collection mode">
                                            <select
                                                name="mode"
                                                defaultValue={
                                                    source.scraper_config_json
                                                        ?.mode ?? "AUTO"
                                                }
                                                className={input}
                                            >
                                                <option>AUTO</option>
                                                <option>PAGE</option>
                                                <option>RSS</option>
                                                <option>SITEMAP</option>
                                            </select>
                                        </Field>
                                        <Field label="Maximum pages">
                                            <input
                                                name="pages"
                                                type="number"
                                                min="1"
                                                max="500"
                                                defaultValue={
                                                    source.scraper_config_json
                                                        ?.max_pages ?? 50
                                                }
                                                className={input}
                                            />
                                        </Field>
                                        <input
                                            type="hidden"
                                            name="depth"
                                            value={
                                                source.scraper_config_json
                                                    ?.max_depth ?? 2
                                            }
                                        />
                                        <Field label="Keywords (comma-separated)">
                                            <input
                                                name="keywords"
                                                defaultValue={source.scraper_config_json?.keywords?.join(
                                                    ", ",
                                                )}
                                                className={input}
                                            />
                                        </Field>
                                        <Field label="Allowed paths (comma-separated)">
                                            <input
                                                name="allowed"
                                                defaultValue={source.scraper_config_json?.allowed_paths?.join(
                                                    ", ",
                                                )}
                                                className={input}
                                            />
                                        </Field>
                                        <Field label="Excluded paths (comma-separated)">
                                            <input
                                                name="excluded"
                                                defaultValue={source.scraper_config_json?.excluded_paths?.join(
                                                    ", ",
                                                )}
                                                className={input}
                                            />
                                        </Field>
                                        <Field label="Feed URL (optional)">
                                            <input
                                                type="url"
                                                name="feed"
                                                defaultValue={
                                                    source.scraper_config_json
                                                        ?.feed_url ?? ""
                                                }
                                                className={input}
                                            />
                                        </Field>
                                        <Field label="Sitemap URL (optional)">
                                            <input
                                                type="url"
                                                name="sitemap"
                                                defaultValue={
                                                    source.scraper_config_json
                                                        ?.sitemap_url ?? ""
                                                }
                                                className={input}
                                            />
                                        </Field>
                                        <label className="self-end pb-2 text-sm">
                                            <input
                                                name="discovery"
                                                type="checkbox"
                                                defaultChecked={
                                                    source.scraper_config_json
                                                        ?.enabled ?? false
                                                }
                                            />{" "}
                                            Discover linked articles
                                        </label>
                                    </>
                                )}
                                <label className="self-end pb-2 text-sm">
                                    <input
                                        name="enabled"
                                        type="checkbox"
                                        defaultChecked={source.enabled}
                                    />{" "}
                                    Enabled
                                </label>
                                <button className="self-end rounded-lg bg-slate-700 px-3 py-2 text-sm">
                                    Save changes
                                </button>
                            </form>
                        </details>
                    </article>
                ))}
            </section>
        </div>
    );
}
