import DisruptionPanel from "@/components/DisruptionPanel";
import ExposureAlert from "@/components/ExposureAlert";
import PlanComparisonMatrix from "@/components/PlanComparisonMatrix";
import PlanRankingTable from "@/components/PlanRankingTable";
import SupplyChainGraph from "@/components/SupplyChainGraph";
import SimulationPanel from "@/components/SimulationPanel";
import ScenarioTable from "@/components/ScenarioTable";
import { getSupplyChainData } from "@/lib/api";
import type { NetworkResponse } from "@/types/network";

type LoadResult =
    | { data: NetworkResponse }
    | { error: string };

async function loadData(): Promise<LoadResult> {
    try {
        return { data: await getSupplyChainData() };
    } catch (error) {
        return {
            error: error instanceof Error ? error.message : "FastAPI is unavailable",
        };
    }
}

export default async function Home() {
    const result = await loadData();

    if ("error" in result) {
        return (
            <main className="flex min-h-screen items-center justify-center bg-slate-950 p-8">
                <section className="rounded-2xl border border-red-800 bg-slate-900 p-8 text-center shadow-2xl shadow-black/30">
                    <h1 className="text-xl font-bold text-slate-100">
                        Supply-chain network unavailable
                    </h1>
                    <p className="mt-2 text-sm text-red-300">{result.error}</p>
                </section>
            </main>
        );
    }

    const { network, shipments, disruptions, exposures, scenarios, plans } = result.data;

    return (
        <main className="min-h-screen bg-slate-950 px-4 py-6 text-slate-100 lg:px-6">
            <header className="mx-auto mb-6 flex max-w-[1800px] flex-wrap items-end justify-between gap-6">
                <div>
                    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
                        PSA ESG Platform
                    </p>
                    <h1 className="mt-2 text-3xl font-bold tracking-tight">
                        Supply-chain network
                    </h1>
                </div>
                <p className="rounded-full border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-400">
                    {network.nodes.length} nodes · {network.edges.length} routes ·{" "}
                    {shipments.length} shipments · {disruptions.length} disruptions
                </p>
            </header>

            <section className="mx-auto grid max-w-[1800px] gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(420px,0.9fr)] lg:items-start">
                <div className="min-w-0 lg:sticky lg:top-6">
                    <SupplyChainGraph
                        network={network}
                        disruptions={disruptions}
                        exposures={exposures}
                    />
                </div>

                <div className="min-w-0 lg:max-h-[calc(100vh-9.5rem)] lg:overflow-y-auto lg:pr-2">
                    {exposures.map((exposure) => {
                        const disruption = disruptions.find(
                            (item) => item.id === exposure.disruption_id,
                        );

                        return disruption ? (
                            <ExposureAlert
                                key={exposure.disruption_id}
                                disruption={disruption}
                                exposure={exposure}
                                network={network}
                            />
                        ) : null;
                    })}
                    <DisruptionPanel disruptions={disruptions} />
                    <SimulationPanel />
                    <ScenarioTable scenarios={scenarios} />
                    <PlanComparisonMatrix plans={plans} scenarios={scenarios} />
                    <PlanRankingTable />
                </div>
            </section>
        </main>
    );
}
