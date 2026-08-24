"use client";

import { useActionState } from "react";

import { rankContingencyPlans } from "@/app/actions";
import LoadingButton from "@/components/LoadingButton";
import type { PlanRankingActionState } from "@/types/plan";

const initialState: PlanRankingActionState = {
    result: null,
    error: null,
};

const currencyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
});

const decimalFormatter = new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
});

type WeightInputProps = {
    label: string;
    name: string;
    defaultValue: number;
};

function WeightInput({ label, name, defaultValue }: WeightInputProps) {
    return (
        <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            {label}
            <input
                name={name}
                type="number"
                min="0"
                step="0.01"
                required
                defaultValue={defaultValue}
                className="mt-1 block w-24 rounded-lg border border-slate-600 bg-slate-950 px-3 py-2 text-sm font-normal text-slate-100"
            />
        </label>
    );
}

export default function PlanRankingTable() {
    const [state, action, pending] = useActionState(
        rankContingencyPlans,
        initialState,
    );

    return (
        <section className="mb-6 overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-xl shadow-black/20">
            <form
                action={action}
                className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-700 bg-slate-900 p-5"
            >
                <div>
                    <h2 className="text-lg font-bold text-slate-100">
                        Deterministic plan ranking
                    </h2>
                    <p className="mt-1 text-sm text-slate-400">
                        Score = w_c × expected cost + w_d × expected delay + w_r × worst-case cost
                    </p>
                </div>
                <div className="flex flex-wrap items-end gap-3">
                    <WeightInput label="Cost weight" name="cost_weight" defaultValue={1} />
                    <WeightInput label="Delay weight" name="delay_weight" defaultValue={100} />
                    <WeightInput label="Risk weight" name="risk_weight" defaultValue={0.25} />
                    <LoadingButton
                        type="submit"
                        disabled={pending}
                        pending={pending}
                        pendingLabel="Ranking plans…"
                        className="rounded-xl bg-indigo-700 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-800 disabled:cursor-wait disabled:opacity-60"
                    >
                        Rank plans
                    </LoadingButton>
                </div>
            </form>

            {state.error && (
                <p className="m-5 rounded-lg bg-red-950/70 p-3 text-sm text-red-300">
                    {state.error}
                </p>
            )}

            <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                    <thead className="bg-slate-800 text-xs uppercase tracking-wide text-slate-400">
                        <tr>
                            <th className="px-5 py-3 font-semibold">Plan</th>
                            <th className="px-5 py-3 font-semibold">Cost</th>
                            <th className="px-5 py-3 font-semibold">Delay</th>
                            <th className="px-5 py-3 font-semibold">Worst case</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700">
                        {state.result?.plans.map((plan) => {
                            const recommended = plan.plan_id === state.result?.recommended_plan;

                            return (
                                <tr key={plan.plan_id} className={recommended ? "bg-emerald-950/50" : undefined}>
                                    <td className="px-5 py-4 font-semibold text-slate-100">
                                        <span className="mr-2 text-slate-400">{plan.rank}.</span>
                                        {plan.plan_name}
                                        {recommended && (
                                            <span className="ml-2 text-amber-500" aria-label="Recommended plan">
                                                ★
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-5 py-4 text-slate-300">
                                        {currencyFormatter.format(plan.expected_cost)}
                                    </td>
                                    <td className="px-5 py-4 text-slate-300">
                                        {decimalFormatter.format(plan.expected_delay)}h
                                    </td>
                                    <td className="px-5 py-4 text-slate-300">
                                        {currencyFormatter.format(plan.worst_case_cost)}
                                    </td>
                                </tr>
                            );
                        }) ?? (
                            <tr>
                                <td colSpan={4} className="px-5 py-8 text-center text-slate-500">
                                    Choose weights and rank the contingency plans.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </section>
    );
}
