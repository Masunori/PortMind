"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
    ["Connection", "/"],
    ["Sources", "/sources"],
    ["Evidence", "/evidence"],
    ["Review", "/review"],
    ["Planning", "/planning"],
] as const;

export default function AppNav() {
    const pathname = usePathname();
    return (
        <header className="border-b border-slate-800 bg-slate-950/95">
            <nav
                className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-4"
                aria-label="Primary navigation"
            >
                <Link href="/" className="font-semibold text-slate-100">
                    AEGIS
                </Link>
                <div className="flex flex-wrap gap-1">
                    {items.map(([label, href]) => {
                        const active =
                            href === "/"
                                ? pathname === href
                                : pathname.startsWith(href);
                        return (
                            <Link
                                key={href}
                                href={href}
                                aria-current={active ? "page" : undefined}
                                className={`rounded-lg px-3 py-2 text-sm ${active ? "bg-sky-600 text-white" : "text-slate-300 hover:bg-slate-900"}`}
                            >
                                {label}
                            </Link>
                        );
                    })}
                </div>
            </nav>
        </header>
    );
}
