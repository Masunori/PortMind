"use client";

import { useEffect } from "react";

export default function PlanningError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        console.error(error);
    }, [error]);
    return (
        <main className="min-h-screen bg-slate-950 px-6 py-16 text-slate-100">
            <div className="mx-auto max-w-xl rounded-2xl border border-red-800 bg-red-950/60 p-6">
                <h1 className="text-xl font-semibold text-red-300">
                    Planning console could not load
                </h1>
                <p className="mt-2 text-sm text-slate-300">
                    No workflow state was changed. Check the platform connection
                    and try again.
                </p>
                <button
                    onClick={reset}
                    className="mt-5 rounded-lg bg-red-700 px-4 py-2 text-sm font-semibold"
                >
                    Try again
                </button>
            </div>
        </main>
    );
}
