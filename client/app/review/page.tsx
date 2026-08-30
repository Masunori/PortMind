import Pagination from "@/components/Pagination";
import ReviewControls from "@/components/ReviewControls";
import { getEvidenceItem, getSignals } from "@/lib/api";

const pageSize = 20;

export default async function ReviewPage({
    searchParams,
}: {
    searchParams: Promise<{ page?: string }>;
}) {
    const { page: pageValue } = await searchParams;
    const parsedPage = Number.parseInt(pageValue ?? "1", 10);
    const page = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1;

    const items = await getSignals(
        "PENDING",
        pageSize + 1,
        (page - 1) * pageSize,
    );
    const hasNext = items.length > pageSize;
    const signals = items.slice(0, pageSize);
    const evidenceIds = [
        ...new Set(signals.flatMap((signal) => signal.evidence_ids)),
    ];
    const evidence = await Promise.all(evidenceIds.map(getEvidenceItem));

    return (
        <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-100">
            <div className="mx-auto max-w-6xl">
                <header className="mb-6">
                    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
                        Human review
                    </p>
                    <h1 className="mt-2 text-3xl font-bold">
                        Signals awaiting review
                    </h1>
                    <p className="mt-2 text-sm text-slate-400">
                        Inspect interpreted evidence and accept or reject signals.
                        Items with resolution or mapping issues can be rejected but
                        cannot be accepted.
                    </p>
                </header>

                <Pagination
                    page={page}
                    hasNext={hasNext}
                    path="/review"
                    className="mb-6"
                />
                <ReviewControls signals={signals} evidence={evidence} />
                <Pagination page={page} hasNext={hasNext} path="/review" />
            </div>
        </main>
    );
}
