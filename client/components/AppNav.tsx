"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
    ["Connection", "/"],
    ["Sources", "/sources"],
    ["Evidence", "/evidence"],
    ["Review", "/review"],
    ["Planning", "/planning"],
    ["Prompts", "/prompts"],
] as const;

export default function AppNav() {
    const pathname = usePathname();
    return (
        <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-slate-950/80 shadow-lg shadow-black/20 backdrop-blur-xl supports-[backdrop-filter]:bg-slate-950/70">
            <nav
                className="mx-auto flex max-w-7xl items-center justify-between gap-5 px-4 py-3 sm:px-6"
                aria-label="Primary navigation"
            >
                <Link
                    href="/"
                    className="group flex shrink-0 items-center gap-3 text-slate-100"
                >
                    <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-600 shadow-lg shadow-sky-950/50 transition-transform group-hover:scale-105">
                        <svg
                            viewBox="0 0 24 24"
                            aria-hidden="true"
                            className="h-5 w-5 fill-none stroke-white"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        >
                            <path d="m7.5 8.5 3-2M13.5 6.5l3 2M17 11.5v2M15.8 16.8l-2.6 1.4M10.8 18.2l-2.6-1.4M7 13.5v-2" />
                            <circle cx="12" cy="5.5" r="2" />
                            <circle cx="18" cy="10" r="2" />
                            <circle cx="18" cy="15.5" r="2" />
                            <circle cx="12" cy="19" r="2" />
                            <circle cx="6" cy="15.5" r="2" />
                            <circle cx="6" cy="10" r="2" />
                        </svg>
                    </span>
                    <span>
                        <span className="block text-sm font-bold tracking-[0.16em]">
                            AEGIS
                        </span>
                        <span className="hidden text-[10px] text-slate-500 sm:block">
                            Risk intelligence
                        </span>
                    </span>
                </Link>
                <div className="flex min-w-0 gap-1 overflow-x-auto rounded-xl border border-slate-800/80 bg-slate-900/60 p-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
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
                                className={`shrink-0 rounded-lg px-3 py-2 text-sm font-medium transition ${active ? "bg-gradient-to-r from-sky-500 to-blue-600 text-white shadow-md shadow-sky-950/40" : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"}`}
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
