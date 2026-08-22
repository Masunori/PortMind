"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

export type SupplyChainNodeData = {
    name: string;
    type: string;
    inventory: number;
    capacity: number;
    disruptionLabels: string[];
    exposureLabels: string[];
};

export type SupplyChainFlowNode = Node<SupplyChainNodeData, "supplyChain">;

const numberFormatter = new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 2,
});

function nodeAccent(type: string, disrupted: boolean, exposed: boolean): string {
    if (disrupted) {
        return "border-red-500 bg-red-950 text-red-100 ring-4 ring-red-900/70";
    }
    if (exposed) {
        return "border-amber-500 bg-amber-950 text-amber-100 ring-4 ring-amber-900/60";
    }

    switch (type.toLowerCase()) {
        case "supplier":
            return "border-amber-600 bg-amber-950 text-amber-100";
        case "port":
            return "border-sky-600 bg-sky-950 text-sky-100";
        case "warehouse":
            return "border-violet-600 bg-violet-950 text-violet-100";
        case "customer":
            return "border-emerald-600 bg-emerald-950 text-emerald-100";
        default:
            return "border-slate-600 bg-slate-900 text-slate-100";
    }
}

export default function SupplyChainNode({ data }: NodeProps<SupplyChainFlowNode>) {
    return (
        <article
            className={`relative w-64 rounded-2xl border-2 px-5 py-4 shadow-lg ${nodeAccent(data.type, data.disruptionLabels.length > 0, data.exposureLabels.length > 0)}`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!h-3 !w-3 !border-2 !border-slate-300 !bg-slate-700"
            />

            <p className="text-xs font-semibold uppercase tracking-[0.18em] opacity-60">
                {data.type}
            </p>
            {data.disruptionLabels.length > 0 && (
                <div className="absolute -right-3 -top-3 rounded-full bg-red-600 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-white shadow-md">
                    Disrupted
                </div>
            )}
            {data.disruptionLabels.length === 0 && data.exposureLabels.length > 0 && (
                <div className="absolute -right-3 -top-3 rounded-full bg-amber-600 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-white shadow-md">
                    Exposed
                </div>
            )}
            <h2 className="mt-1 text-lg font-bold">{data.name}</h2>

            {data.disruptionLabels.map((label) => (
                <p
                    key={label}
                    className="mt-2 rounded-md bg-red-900 px-2 py-1 text-xs font-semibold text-red-200"
                >
                    {label}
                </p>
            ))}
            {data.disruptionLabels.length === 0 && data.exposureLabels.map((label) => (
                <p
                    key={label}
                    className="mt-2 rounded-md bg-amber-900 px-2 py-1 text-xs font-semibold text-amber-200"
                >
                    {label}
                </p>
            ))}

            <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-current/15 pt-3 text-sm">
                <div>
                    <dt className="opacity-60">Inventory</dt>
                    <dd className="font-semibold">{numberFormatter.format(data.inventory)}</dd>
                </div>
                <div>
                    <dt className="opacity-60">Capacity</dt>
                    <dd className="font-semibold">{numberFormatter.format(data.capacity)}</dd>
                </div>
            </dl>

            <Handle
                type="source"
                position={Position.Bottom}
                className="!h-3 !w-3 !border-2 !border-slate-300 !bg-slate-700"
            />
        </article>
    );
}
