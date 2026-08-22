import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
    title: "PSA ESG Platform",
    description: "Supplier sustainability case management platform",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
    return (
        <html lang="en" className="h-full bg-slate-950 antialiased">
            <body className="min-h-full flex flex-col">{children}</body>
        </html>
    );
}
