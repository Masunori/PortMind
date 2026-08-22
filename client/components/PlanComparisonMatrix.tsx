"use client";

import { useActionState } from "react";

import { compareContingencyPlans } from "@/app/actions";
import type { Plan, PlanComparisonActionState } from "@/types/plan";
import type { Scenario } from "@/types/scenario";

const initialState: PlanComparisonActionState = {
    results: null,
    error: null,
};

const currencyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
});

type PlanComparisonMatrixProps = {
    plans: Plan[];
    scenarios: Scenario[];
};

function actionSummary(plan: Plan): string {
    const actionTypes = [...new Set(plan.actions.map((action) => action.type))];
    return actionTypes
        .map((type) => type.toLowerCase().replaceAll("_", " "))
        .join(", ");
}

export default function PlanComparisonMatrix({
    plans,
    scenarios,
}: PlanComparisonMatrixProps) {
    const [state, action, pending] = useActionState(
        compareContingencyPlans,
        initialState,
    );
    const resultByCombination = new Map(
        state.results?.map((result) => [
            `${result.plan_id}:${result.scenario_id}`,
            result,
        ]),
    );

    return (
        <section className="mb-6 overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-xl shadow-black/20">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-700 bg-slate-900 p-5">
                <div>
                    <h2 className="text-lg font-bold text-slate-100">
                        Contingency plan comparison
                    </h2>
                    <p className="mt-1 text-sm text-slate-400">
                        Run {plans.length} plans across {scenarios.length} weighted scenarios
                    </p>
                </div>
                <form action={action}>
                    <button
                        type="submit"
                        disabled={pending || plans.length === 0 || scenarios.length === 0}
                        className="rounded-xl bg-emerald-700 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
                    >
                        {pending ? "Comparing interventions…" : "Compare interventions"}
                    </button>
                </form>
            </div>

            {state.error && (
                <p className="m-5 rounded-lg bg-red-950/70 p-3 text-sm text-red-300">
                    {state.error}
                </p>
            )}

            <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] text-left text-sm">
                    <thead className="bg-slate-800 text-xs uppercase tracking-wide text-slate-400">
                        <tr>
                            <th className="px-5 py-3 font-semibold">Plan</th>
                            {scenarios.map((scenario) => (
                                <th key={scenario.id} className="px-5 py-3 font-semibold">
                                    {scenario.name}
                                    <span className="ml-1 font-normal normal-case text-slate-500">
                                        ({Math.round(scenario.probability * 100)}%)
                                    </span>
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700">
                        {plans.map((plan) => (
                            <tr key={plan.id}>
                                <th className="px-5 py-4 align-top">
                                    <div className="font-semibold text-slate-100">
                                        {plan.name}
                                    </div>
                                    <div className="mt-1 text-xs font-normal capitalize text-slate-500">
                                        {actionSummary(plan)}
                                    </div>
                                </th>
                                {scenarios.map((scenario) => {
                                    const result = resultByCombination.get(
                                        `${plan.id}:${scenario.id}`,
                                    );

                                    return (
                                        <td key={scenario.id} className="px-5 py-4 align-top">
                                            {result ? (
                                                <div className="space-y-1 text-slate-300">
                                                    <div className="font-semibold text-slate-100">
                                                        {currencyFormatter.format(result.total_cost)}
                                                    </div>
                                                    <div>{result.average_lead_time_hours}h lead time</div>
                                                    <div>{result.delay_hours}h delay</div>
                                                </div>
                                            ) : (
                                                <span className="text-slate-400">—</span>
                                            )}
                                        </td>
                                    );
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </section>
    );
}
