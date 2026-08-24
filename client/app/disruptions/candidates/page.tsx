import Link from "next/link";

import CandidateInbox from "@/components/CandidateInbox";
import { getCandidateExposure, getCandidates } from "@/lib/api";

export default async function CandidatesPage() {
    const candidates = await getCandidates();
    const items = await Promise.all(
        candidates.map(async (candidate) => ({
            candidate,
            exposure: candidate.validation_status === "VALIDATED"
                ? await getCandidateExposure(candidate.id).catch(() => null)
                : null,
        })),
    );

    return (
        <main className="min-h-screen bg-slate-950 px-4 py-6 text-slate-100 lg:px-8">
            <header className="mx-auto mb-6 flex max-w-[1400px] flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">Operations inbox</p>
                    <h1 className="mt-2 text-3xl font-bold">Potential disruptions</h1>
                </div>
                <nav className="flex gap-2">
                    <Link href="/sources" className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-900">Sources</Link>
                    <Link href="/" className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-900">Network workspace</Link>
                </nav>
            </header>
            <div className="mx-auto max-w-[1400px]">
                <CandidateInbox items={items} />
            </div>
        </main>
    );
}
