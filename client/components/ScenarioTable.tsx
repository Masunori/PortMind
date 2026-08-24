"use client";

import { useActionState } from "react";

import { runAllScenarios } from "@/app/actions";
import LoadingButton from "@/components/LoadingButton";
import type { ScenarioActionState, Scenario } from "@/types/scenario";

const initialState: ScenarioActionState = {
    results: null,
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

type ScenarioTableProps = {
    scenarios: Scenario[];
};

export default function ScenarioTable({ scenarios }: ScenarioTableProps) {
    const [state, action, pending] = useActionState(runAllScenarios, initialState);
    const resultsById = new Map(
        state.results?.map((result) => [result.scenario_id, result]),
    );

    return (
        <section className="mb-6 overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-xl shadow-black/20">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-700 bg-slate-900 p-5">
                <div>
                    <h2 className="text-lg font-bold text-slate-100">
                        Closure scenarios
                    </h2>
                    <p className="mt-1 text-sm text-slate-400">
                        Compare all weighted scenarios against the 42h baseline
                    </p>
                </div>
                <form action={action}>
                    <LoadingButton
                        type="submit"
                        disabled={pending || scenarios.length === 0}
                        pending={pending}
                        pendingLabel="Running scenarios…"
                        className="rounded-xl bg-sky-700 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-sky-800 disabled:cursor-wait disabled:opacity-60"
                    >
                        Run all scenarios
                    </LoadingButton>
                </form>
            </div>

            {state.error && (
                <p className="m-5 rounded-lg bg-red-950/70 p-3 text-sm text-red-300">
                    {state.error}
                </p>
            )}

            <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                    <thead className="bg-slate-800 text-xs uppercase tracking-wide text-slate-400">
                        <tr>
                            <th className="px-5 py-3 font-semibold">Scenario</th>
                            <th className="px-5 py-3 font-semibold">Probability</th>
                            <th className="px-5 py-3 font-semibold">Cost</th>
                            <th className="px-5 py-3 font-semibold">Delay</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700">
                        {scenarios.map((scenario) => {
                            const result = resultsById.get(scenario.id);

                            return (
                                <tr key={scenario.id}>
                                    <td className="px-5 py-4 font-semibold text-slate-100">
                                        {scenario.name}
                                    </td>
                                    <td className="px-5 py-4 text-slate-300">
                                        {Math.round(scenario.probability * 100)}%
                                    </td>
                                    <td className="px-5 py-4 text-slate-300">
                                        {result
                                            ? currencyFormatter.format(result.total_cost)
                                            : "—"}
                                    </td>
                                    <td className="px-5 py-4 text-slate-300">
                                        {result
                                            ? `${hoursFormatter.format(result.delay_hours)}h`
                                            : "—"}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </section>
    );
}
