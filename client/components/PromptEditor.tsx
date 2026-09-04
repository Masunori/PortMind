"use client";

import { useState } from "react";

import type { AgentName, AgentPrompt } from "@/types/prompt";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const details: Record<
    AgentName,
    { title: string; description: string; accent: string }
> = {
    filter: {
        title: "Filter agent",
        description:
            "Controls relevance, safety screening, and evidence triage.",
        accent: "from-cyan-400 to-sky-500",
    },
    interpreter: {
        title: "Interpreter agent",
        description:
            "Guides signal extraction and interpretation from accepted evidence.",
        accent: "from-violet-400 to-fuchsia-500",
    },
    planner: {
        title: "Single planner",
        description: "Shapes proposals when planning mode uses one planner.",
        accent: "from-amber-300 to-orange-500",
    },
    planner_1: {
        title: "Panel agent 1 · Continuity",
        description:
            "Prioritizes operational continuity, service, and recovery time.",
        accent: "from-emerald-300 to-teal-500",
    },
    planner_2: {
        title: "Panel agent 2 · Cost",
        description:
            "Prioritizes resource efficiency, affordability, and cost control.",
        accent: "from-yellow-300 to-amber-500",
    },
    planner_3: {
        title: "Panel agent 3 · Resilience",
        description:
            "Prioritizes robust mitigation, redundancy, and uncertainty.",
        accent: "from-blue-300 to-indigo-500",
    },
    planner_4: {
        title: "Panel agent 4 · Responsiveness",
        description:
            "Prioritizes implementation speed and near-term risk reduction.",
        accent: "from-pink-300 to-rose-500",
    },
    planner_5: {
        title: "Panel agent 5 · Sustainability",
        description:
            "Prioritizes durable, responsible, long-term improvements.",
        accent: "from-lime-300 to-green-500",
    },
};

export default function PromptEditor({
    initialPrompts,
}: {
    initialPrompts: AgentPrompt[];
}) {
    const [prompts, setPrompts] = useState(initialPrompts);
    const [selected, setSelected] = useState<AgentName>(
        initialPrompts[0]?.agent ?? "filter",
    );
    const [drafts, setDrafts] = useState<Record<AgentName, string>>(
        () =>
            Object.fromEntries(
                initialPrompts.map((item) => [item.agent, item.prompt]),
            ) as Record<AgentName, string>,
    );
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState<{
        text: string;
        error: boolean;
    } | null>(null);
    const current = prompts.find((item) => item.agent === selected);

    async function request(method: "PUT" | "DELETE") {
        setBusy(true);
        setMessage(null);
        try {
            const response = await fetch(
                `${apiUrl}/api/settings/prompts/${selected}`,
                {
                    method,
                    headers:
                        method === "PUT"
                            ? { "Content-Type": "application/json" }
                            : undefined,
                    body:
                        method === "PUT"
                            ? JSON.stringify({ prompt: drafts[selected] })
                            : undefined,
                },
            );
            const body = (await response.json().catch(() => null)) as
                | AgentPrompt
                | { detail?: string }
                | null;
            if (!response.ok || !body || !("agent" in body)) {
                throw new Error(
                    body && "detail" in body
                        ? body.detail
                        : `Request failed (${response.status})`,
                );
            }
            setPrompts((items) =>
                items.map((item) => (item.agent === selected ? body : item)),
            );
            setDrafts((items) => ({ ...items, [selected]: body.prompt }));
            setMessage({
                text:
                    method === "PUT"
                        ? "Prompt saved. New agent runs will use it."
                        : "Default prompt restored.",
                error: false,
            });
        } catch (error) {
            setMessage({
                text:
                    error instanceof Error
                        ? error.message
                        : "Unable to update prompt.",
                error: true,
            });
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="mt-10 grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
            <aside className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-2 shadow-xl shadow-black/10 backdrop-blur">
                {prompts.map((item) => {
                    const meta = details[item.agent];
                    const active = selected === item.agent;
                    return (
                        <button
                            key={item.agent}
                            type="button"
                            onClick={() => {
                                setSelected(item.agent);
                                setMessage(null);
                            }}
                            className={`flex w-full items-start gap-3 rounded-xl border px-3 py-4 text-left ${active ? "border-slate-700 bg-slate-800/90" : "border-transparent hover:bg-slate-800/50"}`}
                        >
                            <span
                                className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-gradient-to-br ${meta.accent}`}
                            />
                            <span className="min-w-0">
                                <span className="block font-semibold text-slate-100">
                                    {meta.title}
                                </span>
                                <span className="mt-1 block text-xs leading-5 text-slate-400">
                                    {item.is_custom
                                        ? "Custom prompt"
                                        : "Platform default"}
                                </span>
                            </span>
                        </button>
                    );
                })}
            </aside>
            <section className="overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900 shadow-2xl shadow-black/20">
                <div className="border-b border-slate-800 bg-gradient-to-r from-slate-900 to-slate-900/40 px-6 py-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                            <h2 className="text-xl font-semibold text-white">
                                {details[selected].title}
                            </h2>
                            <p className="mt-1 text-sm text-slate-400">
                                {details[selected].description}
                            </p>
                        </div>
                        <span
                            className={`rounded-full border px-3 py-1 text-xs font-medium ${current?.is_custom ? "border-sky-700/60 bg-sky-950/60 text-sky-300" : "border-slate-700 bg-slate-950/60 text-slate-400"}`}
                        >
                            {current?.is_custom ? "Customized" : "Default"}
                        </span>
                    </div>
                </div>
                <div className="p-6">
                    <label
                        htmlFor="system-prompt"
                        className="text-sm font-medium text-slate-200"
                    >
                        System prompt
                    </label>
                    <p className="mt-1 text-xs text-slate-500">
                        Changes apply to future Gemini requests; structured
                        output and contract validation remain enforced.
                    </p>
                    <textarea
                        id="system-prompt"
                        value={drafts[selected] ?? ""}
                        onChange={(event) =>
                            setDrafts((items) => ({
                                ...items,
                                [selected]: event.target.value,
                            }))
                        }
                        className="mt-4 min-h-80 w-full resize-y rounded-xl border border-slate-700 bg-slate-950/80 p-4 font-mono text-sm leading-6 text-slate-200 shadow-inner outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20"
                        spellCheck={false}
                    />
                    <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                        <div
                            aria-live="polite"
                            className={`text-sm ${message?.error ? "text-red-300" : "text-emerald-300"}`}
                        >
                            {message?.text}
                        </div>
                        <div className="flex gap-2">
                            <button
                                type="button"
                                disabled={busy || !current?.is_custom}
                                onClick={() => request("DELETE")}
                                className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 disabled:opacity-40"
                            >
                                Restore default
                            </button>
                            <button
                                type="button"
                                disabled={
                                    busy ||
                                    !drafts[selected]?.trim() ||
                                    drafts[selected] === current?.prompt
                                }
                                onClick={() => request("PUT")}
                                className="rounded-lg border border-sky-500/40 bg-sky-500 px-5 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"
                            >
                                {busy ? "Saving…" : "Save prompt"}
                            </button>
                        </div>
                    </div>
                </div>
            </section>
        </div>
    );
}
