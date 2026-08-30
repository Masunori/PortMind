import Link from "next/link";

interface PaginationProps {
    page: number;
    hasNext: boolean;
    path: string;
    params?: Record<string, string>;
    className?: string;
}

export default function Pagination({
    page,
    hasNext,
    path,
    params = {},
    className = "",
}: PaginationProps) {
    function href(target: number) {
        const query = new URLSearchParams(params);

        if (target > 1) {
            query.set("page", String(target));
        }

        const value = query.toString();
        return value ? `${path}?${value}` : path;
    }

    return (
        <nav
            aria-label="Pagination"
            className={`mt-6 grid grid-cols-3 items-center ${className}`}
        >
            {page > 1 ? (
                <Link
                    href={href(page - 1)}
                    className="justify-self-start rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-900"
                >
                    Previous
                </Link>
            ) : (
                <span />
            )}

            <span className="justify-self-center text-sm text-slate-400">
                Page {page}
            </span>

            {hasNext ? (
                <Link
                    href={href(page + 1)}
                    className="justify-self-end rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-900"
                >
                    Next
                </Link>
            ) : (
                <span />
            )}
        </nav>
    );
}
