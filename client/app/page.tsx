import { getClientConnection, type ClientConnection } from "@/lib/api";

async function connection(): Promise<ClientConnection> {
    try {
        return await getClientConnection();
    } catch {
        return {
            status: "degraded",
            client_id: null,
            context_version: null,
            schema_version: null,
            state_version: null,
            capability_version: null,
            last_successful_response_at: null,
            error_code: "PLATFORM_UNAVAILABLE",
        };
    }
}

export default async function Home() {
    const client = await connection();
    const versions = [
        ["Context", client.context_version],
        ["Schema", client.schema_version],
        ["State", client.state_version],
        ["Capabilities", client.capability_version],
    ];
    return (
        <main className="min-h-screen bg-slate-950 px-6 py-12 text-slate-100">
            <div className="mx-auto max-w-5xl">
                <header className="flex flex-wrap items-end justify-between gap-6">
                    <div>
                        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
                            AEGIS Platform
                        </p>
                        <h1 className="mt-2 text-4xl font-bold">
                            Client connection
                        </h1>
                        <p className="mt-3 max-w-2xl text-slate-400">
                            Operational data and authoritative simulation remain
                            in the connected client. This platform stores
                            evidence, reviewed signals, immutable experiments,
                            and normalized result copies.
                        </p>
                    </div>
                    <span
                        className={`rounded-full border px-4 py-2 text-sm ${client.status === "ok" ? "border-emerald-700 bg-emerald-950 text-emerald-300" : "border-red-800 bg-red-950 text-red-300"}`}
                    >
                        {client.status === "ok"
                            ? "Connected"
                            : "Connection degraded"}
                    </span>
                </header>
                <section className="mt-10 rounded-2xl border border-slate-800 bg-slate-900 p-6">
                    <p className="text-sm text-slate-400">Client identity</p>
                    <p className="mt-1 text-xl font-semibold">
                        {client.client_id ?? "Unavailable"}
                    </p>
                    <dl className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                        {versions.map(([label, value]) => (
                            <div
                                key={label}
                                className="rounded-xl bg-slate-950 p-4"
                            >
                                <dt className="text-xs uppercase tracking-wide text-slate-500">
                                    {label}
                                </dt>
                                <dd className="mt-2 font-mono text-sm text-sky-300">
                                    {value ?? "—"}
                                </dd>
                            </div>
                        ))}
                    </dl>
                    <p className="mt-5 text-xs text-slate-500">
                        {client.last_successful_response_at
                            ? `Last successful response: ${new Date(client.last_successful_response_at).toLocaleString()}`
                            : `Diagnostic: ${client.error_code ?? "No successful response"}`}
                    </p>
                </section>
            </div>
        </main>
    );
}
