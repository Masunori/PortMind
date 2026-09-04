import SourceControls from "@/components/SourceControls";
import { getSchedulingStatus, getSources } from "@/lib/api";

export default async function SourcesPage() {
    const [sources, scheduling] = await Promise.all([
        getSources(),
        getSchedulingStatus(),
    ]);
    return (
        <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-100">
            <div className="mx-auto max-w-6xl">
                <header>
                    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
                        Evidence ingestion
                    </p>
                    <h1 className="mt-2 text-3xl font-bold">
                        Sources and scrapers
                    </h1>
                    <p className="mt-2 text-sm text-slate-400">
                        Configure user-owned collection sources, schedules,
                        discovery limits, and manual collection.
                    </p>
                </header>
                <div className="mt-8">
                    <SourceControls sources={sources} scheduling={scheduling} />
                </div>
            </div>
        </main>
    );
}
