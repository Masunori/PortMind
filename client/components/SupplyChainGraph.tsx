"use client";

import { useMemo } from "react";
import {
    Background,
    BackgroundVariant,
    Controls,
    MarkerType,
    ReactFlow,
    type Edge as FlowEdge,
    type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import SupplyChainNode, {
    type SupplyChainFlowNode,
} from "@/components/SupplyChainNode";
import type { Disruption, ExposureAnalysis } from "@/types/disruption";
import type { Edge, Network } from "@/types/network";

type SupplyChainGraphProps = {
    network: Network;
    disruptions: Disruption[];
    exposures: ExposureAnalysis[];
};

const nodeTypes: NodeTypes = {
    supplyChain: SupplyChainNode,
};

const currencyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
});

function titleCase(value: string): string {
    return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}

function disruptionLabel(disruption: Disruption): string {
    const name = disruption.type
        .toLowerCase()
        .split("_")
        .map(titleCase)
        .join(" ");
    return `${name} · ${disruption.start_time}–${disruption.end_time}h`;
}

function edgeLabel(
    edge: Edge,
    disruptions: Disruption[],
    exposed: boolean,
) {
    const disrupted = disruptions.length > 0;

    return (
        <div
            className={`rounded-lg border px-3 py-2 text-center text-xs font-semibold leading-5 shadow-lg shadow-black/30 ${disrupted ? "border-red-700 bg-red-950/95 text-red-100" : exposed ? "border-amber-700 bg-amber-950/95 text-amber-100" : "border-slate-600 bg-slate-900/95 text-slate-200"}`}
        >
            <div>{edge.transit_time_hours}h</div>
            <div>{currencyFormatter.format(edge.cost)}</div>
            <div className="text-slate-400">{titleCase(edge.mode)}</div>
            {disruptions.map((disruption) => (
                <div key={disruption.id} className="mt-1 border-t border-red-800 pt-1 text-red-300">
                    {disruptionLabel(disruption)}
                </div>
            ))}
            {!disrupted && exposed && (
                <div className="mt-1 border-t border-amber-800 pt-1 text-amber-300">
                    Downstream exposure
                </div>
            )}
        </div>
    );
}

function calculateLevels(network: Network): Map<string, number> {
    const incoming = new Map(network.nodes.map((node) => [node.id, 0]));
    const outgoing = new Map<string, string[]>();

    for (const edge of network.edges) {
        incoming.set(edge.target_id, (incoming.get(edge.target_id) ?? 0) + 1);
        outgoing.set(edge.source_id, [
            ...(outgoing.get(edge.source_id) ?? []),
            edge.target_id,
        ]);
    }

    const queue = network.nodes
        .filter((node) => incoming.get(node.id) === 0)
        .map((node) => node.id);
    const levels = new Map(queue.map((id) => [id, 0]));

    for (let index = 0; index < queue.length; index += 1) {
        const sourceId = queue[index];
        const sourceLevel = levels.get(sourceId) ?? 0;

        for (const targetId of outgoing.get(sourceId) ?? []) {
            levels.set(targetId, Math.max(levels.get(targetId) ?? 0, sourceLevel + 1));
            incoming.set(targetId, (incoming.get(targetId) ?? 1) - 1);

            if (incoming.get(targetId) === 0) {
                queue.push(targetId);
            }
        }
    }

    for (const node of network.nodes) {
        if (!levels.has(node.id)) {
            levels.set(node.id, levels.size);
        }
    }

    return levels;
}

function buildNodes(
    network: Network,
    disruptions: Disruption[],
    exposures: ExposureAnalysis[],
): SupplyChainFlowNode[] {
    const enabledDisruptions = disruptions.filter((disruption) => disruption.enabled);
    const levels = calculateLevels(network);
    const nodesByLevel = new Map<number, typeof network.nodes>();

    for (const node of network.nodes) {
        const level = levels.get(node.id) ?? 0;
        nodesByLevel.set(level, [...(nodesByLevel.get(level) ?? []), node]);
    }

    return [...nodesByLevel.entries()].flatMap(([level, nodes]) =>
        nodes.map((node, index) => ({
            id: node.id,
            type: "supplyChain",
            position: {
                x: (index - (nodes.length - 1) / 2) * 360,
                y: level * 220,
            },
            data: {
                name: node.name,
                type: node.type,
                inventory: node.inventory,
                capacity: node.capacity,
                disruptionLabels: enabledDisruptions
                    .filter((disruption) => disruption.affected_node_ids.includes(node.id))
                    .map(disruptionLabel),
                exposureLabels: exposures
                    .filter((exposure) => exposure.affected_nodes.includes(node.id))
                    .map((exposure) => `Downstream exposure · ${exposure.disruption_id}`),
            },
        })),
    );
}

function disruptionsForEdge(
    edge: Edge,
    disruptions: Disruption[],
): Disruption[] {
    return disruptions.filter((disruption) =>
        disruption.affected_edge_ids.includes(edge.id)
        || disruption.affected_node_ids.includes(edge.source_id)
        || (
            disruption.effects.capacity_multiplier !== undefined
            && disruption.affected_node_ids.includes(edge.target_id)
        ),
    );
}

function buildEdges(
    network: Network,
    disruptions: Disruption[],
    exposures: ExposureAnalysis[],
): FlowEdge[] {
    const enabledDisruptions = disruptions.filter((disruption) => disruption.enabled);

    return network.edges.map((edge) => {
        const edgeDisruptions = disruptionsForEdge(edge, enabledDisruptions);
        const disrupted = edgeDisruptions.length > 0;
        const exposed = exposures.some((exposure) =>
            exposure.affected_edges.includes(edge.id),
        );

        return {
            id: edge.id,
            source: edge.source_id,
            target: edge.target_id,
            label: edgeLabel(edge, edgeDisruptions, exposed),
            markerEnd: {
                type: MarkerType.ArrowClosed,
                color: disrupted ? "#dc2626" : exposed ? "#d97706" : "#475569",
            },
            style: {
                stroke: disrupted ? "#ef4444" : exposed ? "#f59e0b" : "#64748b",
                strokeWidth: disrupted || exposed ? 3 : 2,
                strokeDasharray: disrupted || exposed ? "8 5" : undefined,
            },
            animated: disrupted || exposed,
        };
    });
}

export default function SupplyChainGraph({
    network,
    disruptions,
    exposures,
}: SupplyChainGraphProps) {
    const nodes = useMemo(
        () => buildNodes(network, disruptions, exposures),
        [network, disruptions, exposures],
    );
    const edges = useMemo(
        () => buildEdges(network, disruptions, exposures),
        [network, disruptions, exposures],
    );

    return (
        <div className="h-[70vh] min-h-[600px] overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl shadow-black/30 lg:h-[calc(100vh-9.5rem)]">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable={false}
                fitView
                fitViewOptions={{ padding: 0.2 }}
                minZoom={0.35}
                maxZoom={1.5}
            >
                <Background
                    variant={BackgroundVariant.Dots}
                    gap={20}
                    size={1.5}
                    color="#334155"
                />
                <Controls showInteractive={false} />
            </ReactFlow>
        </div>
    );
}
