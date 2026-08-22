"use client";

import { useActionState } from "react";

import {
    injectBaselineDisruption,
    toggleBaselineDisruption,
} from "@/app/actions";
import type { Disruption, DisruptionActionState } from "@/types/disruption";

const initialState: DisruptionActionState = {
    disruption: null,
    error: null,
};

type DisruptionPanelProps = {
    disruptions: Disruption[];
};

export default function DisruptionPanel({ disruptions }: DisruptionPanelProps) {
    const configuredDisruption = disruptions.find(
        (disruption) => disruption.id === "hai-phong-port-congestion",
    );
    const [injectState, injectAction, injecting] = useActionState(
        injectBaselineDisruption,
        initialState,
    );
    const [toggleState, toggleAction, toggling] = useActionState(
        toggleBaselineDisruption,
        initialState,
    );
    const error = injectState.error ?? toggleState.error;

    return (
        <section className="mb-6 rounded-2xl border border-amber-800 bg-amber-950/40 p-5 shadow-xl shadow-black/20">
            <div className="flex flex-wrap items-center justify-between gap-5">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-400">
                        Inject disruption
                    </p>
                    <dl className="mt-3 grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                        <dt className="text-slate-400">Type</dt>
                        <dd className="font-semibold text-slate-100">Port congestion</dd>
                        <dt className="text-slate-400">Target</dt>
                        <dd className="font-semibold text-slate-100">Hai Phong</dd>
                        <dt className="text-slate-400">Duration</dt>
                        <dd className="font-semibold text-slate-100">48h</dd>
                        <dt className="text-slate-400">Severity</dt>
                        <dd className="font-semibold text-slate-100">2× delay</dd>
                    </dl>
                </div>

                {configuredDisruption ? (
                    <form action={toggleAction}>
                        <input
                            type="hidden"
                            name="enabled"
                            value={configuredDisruption.enabled ? "false" : "true"}
                        />
                        <button
                            type="submit"
                            disabled={toggling}
                            aria-pressed={configuredDisruption.enabled}
                            className={`rounded-xl px-5 py-3 text-sm font-semibold text-white shadow-sm transition disabled:cursor-wait disabled:opacity-60 ${configuredDisruption.enabled ? "bg-red-600 hover:bg-red-700" : "bg-emerald-600 hover:bg-emerald-700"}`}
                        >
                            {toggling
                                ? "Updating…"
                                : configuredDisruption.enabled
                                    ? "Disable disruption"
                                    : "Enable disruption"}
                        </button>
                    </form>
                ) : (
                    <form action={injectAction}>
                        <button
                            type="submit"
                            disabled={injecting}
                            className="rounded-xl bg-amber-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-amber-700 disabled:cursor-wait disabled:opacity-60"
                        >
                            {injecting ? "Injecting…" : "Inject"}
                        </button>
                    </form>
                )}
            </div>

            {configuredDisruption && (
                <p
                    className={`mt-4 rounded-lg p-3 text-sm font-medium ${configuredDisruption.enabled ? "bg-red-950 text-red-300" : "bg-slate-800 text-slate-300"}`}
                >
                    Status: {configuredDisruption.enabled ? "Active" : "Inactive"}
                </p>
            )}

            {error && (
                <p className="mt-4 rounded-lg bg-red-950 p-3 text-sm text-red-300">
                    {error}
                </p>
            )}
            {injectState.disruption && (
                <p className="mt-4 rounded-lg bg-emerald-950 p-3 text-sm font-medium text-emerald-300">
                    Disruption active. Run the baseline simulation again to compare results.
                </p>
            )}
        </section>
    );
}
