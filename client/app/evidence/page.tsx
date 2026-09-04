import EvidenceControls from "@/components/EvidenceControls";
import Pagination from "@/components/Pagination";
import { getEvidence, getSources } from "@/lib/api";

const pageSize = 20;

export default async function EvidencePage({
    searchParams,
}: {
    searchParams: Promise<{
        view?: string;
        page?: string;
        duplicates?: string;
    }>;
}) {
    const {
        view,
        page: pageValue,
        duplicates: duplicatesValue,
    } = await searchParams;
    const archived = view === "archive";
    const includeDuplicates = duplicatesValue === "true";
    const parsedPage = Number.parseInt(pageValue ?? "1", 10);
    const page = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1;

    const [items, sources] = await Promise.all([
        getEvidence(
            archived,
            pageSize + 1,
            (page - 1) * pageSize,
            includeDuplicates,
        ),
        getSources(),
    ]);
    const hasNext = items.length > pageSize;
    const evidence = items.slice(0, pageSize);
    const paginationParams: Record<string, string> = archived
        ? { view: "archive" }
        : {};
    if (includeDuplicates) paginationParams.duplicates = "true";

    return (
        <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-100">
            <div className="mx-auto max-w-6xl">
                <header>
                    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
                        Evidence ingestion
                    </p>
                    <h1 className="mt-2 text-3xl font-bold">
                        Evidence workspace
                    </h1>
                    <p className="mt-2 text-sm text-slate-400">
                        Create, upload, edit, retain, redact, archive, and
                        delete evidence under audit protections.
                    </p>
                </header>

                <div className="my-6 flex gap-2">
                    <a
                        href="/evidence"
                        className={`rounded-lg px-4 py-2 text-sm ${
                            !archived ? "bg-sky-600" : "bg-slate-900"
                        }`}
                    >
                        Inbox
                    </a>
                    <a
                        href="/evidence?view=archive"
                        className={`rounded-lg px-4 py-2 text-sm ${
                            archived ? "bg-sky-600" : "bg-slate-900"
                        }`}
                    >
                        Archive
                    </a>
                    <a
                        href={`/evidence?${new URLSearchParams({
                            ...(archived ? { view: "archive" } : {}),
                            ...(includeDuplicates
                                ? {}
                                : { duplicates: "true" }),
                        })}`}
                        className={`rounded-lg px-4 py-2 text-sm ${includeDuplicates ? "bg-violet-700" : "bg-slate-900"}`}
                    >
                        {includeDuplicates
                            ? "Hide duplicates"
                            : "Include duplicates"}
                    </a>
                </div>

                <Pagination
                    page={page}
                    hasNext={hasNext}
                    path="/evidence"
                    params={paginationParams}
                    className="mb-6"
                />
                <EvidenceControls
                    evidence={evidence}
                    sources={sources}
                    archived={archived}
                />
                <Pagination
                    page={page}
                    hasNext={hasNext}
                    path="/evidence"
                    params={paginationParams}
                />
            </div>
        </main>
    );
}
