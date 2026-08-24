import NetworkManager from "@/components/NetworkManager";
import { getNetwork, getSchemas, getSimulationRules } from "@/lib/api";

export default async function NetworkManagementPage() {
    const [network, schemas, rules] = await Promise.all([
        getNetwork(),
        getSchemas(),
        getSimulationRules(),
    ]);

    return (
        <main className="min-h-screen bg-slate-950 p-6 text-slate-100">
            <NetworkManager
                initialNetwork={network}
                initialSchemas={schemas}
                initialRules={rules}
            />
        </main>
    );
}
