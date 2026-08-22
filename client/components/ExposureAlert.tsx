import type { Disruption, ExposureAnalysis } from "@/types/disruption";
import type { Network } from "@/types/network";

type ExposureAlertProps = {
    disruption: Disruption;
    exposure: ExposureAnalysis;
    network: Network;
};

export default function ExposureAlert({
    disruption,
    exposure,
    network,
}: ExposureAlertProps) {
    const targetName = network.nodes.find((node) =>
        disruption.affected_node_ids.includes(node.id),
    )?.name ?? "Network";
    const disruptionName = disruption.type
        .toLowerCase()
        .split("_")
        .join(" ");

    return (
        <aside className="mb-6 rounded-2xl border-2 border-amber-700 bg-amber-950/50 p-5 shadow-xl shadow-black/20">
            <p className="text-xs font-black uppercase tracking-[0.22em] text-amber-400">
                Warning
            </p>
            <h2 className="mt-2 text-xl font-bold capitalize text-amber-100">
                {targetName.replace(/ port$/i, "")} {disruptionName.replace("port ", "")}
            </h2>
            <div className="mt-4 flex flex-wrap gap-3 text-sm font-semibold text-amber-100">
                <span className="rounded-full bg-amber-900 px-4 py-2">
                    {exposure.affected_shipments.length} shipment
                    {exposure.affected_shipments.length === 1 ? "" : "s"} exposed
                </span>
                <span className="rounded-full bg-amber-900 px-4 py-2">
                    {exposure.affected_customers.length} customer
                    {exposure.affected_customers.length === 1 ? "" : "s"} potentially affected
                </span>
            </div>
        </aside>
    );
}
