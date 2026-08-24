import Link from "next/link";

import SourceManager from "@/components/SourceManager";
import { getDocumentAssessment, getDocuments, getSources } from "@/lib/api";

export default async function SourcesPage() {
    const [sources, documents] = await Promise.all([getSources(), getDocuments()]);
    const documentItems = await Promise.all(
        documents.map(async (document) => ({
            document,
            assessment: await getDocumentAssessment(document.id).catch(() => null),
        })),
    );

    return (
        <main className="min-h-screen bg-slate-950 px-4 py-6 text-slate-100 lg:px-8">
            <header className="mx-auto mb-6 flex max-w-[1600px] items-end justify-between gap-4">
                <div>
                    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">Intelligence ingestion</p>
                    <h1 className="mt-2 text-3xl font-bold">Sources and documents</h1>
                </div>
                <nav className="flex gap-2">
                    <Link href="/disruptions/candidates" className="rounded-lg border border-sky-800 px-4 py-2 text-sm text-sky-300 hover:bg-sky-950">Operations inbox</Link>
                    <Link href="/" className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-900">Network workspace</Link>
                </nav>
            </header>
            <div className="mx-auto max-w-[1600px]">
                <SourceManager initialSources={sources} documentItems={documentItems} />
            </div>
        </main>
    );
}
