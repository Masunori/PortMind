"use client";

import { useActionState } from "react";

import { runBaselineSimulation } from "@/app/actions";
import type { SimulationActionState } from "@/types/simulation";

const initialState: SimulationActionState = {
    result: null,
    error: null,
};

const currencyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
});

const hoursFormatter = new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
});

export default function SimulationPanel() {
    const [state, action, pending] = useActionState(
        runBaselineSimulation,
        initialState,
    );

    return (
        <section className="mb-6 rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-xl shadow-black/20">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <h2 className="text-lg font-bold text-slate-100">Baseline simulation</h2>
                    <p className="mt-1 text-sm text-slate-400">
                        Deterministic 168-hour horizon
                    </p>
                </div>

                <form action={action}>
                    <button
                        type="submit"
                        disabled={pending}
                        className="rounded-xl bg-sky-700 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-sky-800 disabled:cursor-wait disabled:opacity-60"
                    >
                        {pending ? "Running simulation…" : "Run baseline simulation"}
                    </button>
                </form>
            </div>

            {state.error && (
                <p className="mt-4 rounded-lg bg-red-950/70 p-3 text-sm text-red-300">
                    {state.error}
                </p>
            )}

            {state.result && (
                <dl className="mt-5 grid gap-4 border-t border-slate-700 pt-5 sm:grid-cols-3">
                    <div>
                        <dt className="text-sm text-slate-400">Total Cost</dt>
                        <dd className="mt-1 text-2xl font-bold text-slate-100">
                            {currencyFormatter.format(state.result.total_cost)}
                        </dd>
                    </div>
                    <div>
                        <dt className="text-sm text-slate-400">Average Lead Time</dt>
                        <dd className="mt-1 text-2xl font-bold text-slate-100">
                            {hoursFormatter.format(state.result.average_lead_time_hours)}h
                        </dd>
                    </div>
                    <div>
                        <dt className="text-sm text-slate-400">Late Shipments</dt>
                        <dd className="mt-1 text-2xl font-bold text-slate-100">
                            {state.result.late_shipments}
                        </dd>
                    </div>
                </dl>
            )}
        </section>
    );
}
