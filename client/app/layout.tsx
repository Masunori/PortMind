import type { Metadata } from "next";
import AppNav from "@/components/AppNav";
import "./globals.css";

export const metadata: Metadata = {
    title: "AEGIS Platform",
    description: "Evidence-driven risk simulation and contingency planning platform",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
    return (
        <html lang="en" className="h-full bg-slate-950 antialiased">
            <body className="min-h-full flex flex-col"><AppNav />{children}</body>
        </html>
    );
}
