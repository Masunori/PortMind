import PlanningConsole from "@/components/PlanningConsole";
import {
    getClientConnection,
    getPlanningCycles,
    getSignals,
    type ClientConnection,
} from "@/lib/api";
import type { GenerationEntity, PlanningCycle } from "@/types/planning";

export default async function PlanningPage() {
    const [connectionResult, cyclesResult, signalsResult] =
        await Promise.allSettled([
            getClientConnection(),
            getPlanningCycles(),
            getSignals("ACCEPTED", 100, 0),
        ]);
    const connection: ClientConnection =
        connectionResult.status === "fulfilled"
            ? connectionResult.value
            : {
                  status: "degraded",
                  client_id: null,
                  context_version: null,
                  schema_version: null,
                  state_version: null,
                  capability_version: null,
                  last_successful_response_at: null,
                  error_code: "PLATFORM_UNAVAILABLE",
              };
    const cycles: PlanningCycle[] =
        cyclesResult.status === "fulfilled" ? cyclesResult.value : [];
    const signals =
        signalsResult.status === "fulfilled" ? signalsResult.value : [];
    const entityScope = [
        ...new Map(
            signals
                .flatMap((signal) => signal.entities)
                .filter(
                    (entity) =>
                        entity.is_target &&
                        entity.entity_id &&
                        entity.entity_type,
                )
                .map((entity) => [
                    entity.entity_id,
                    {
                        entity_id: entity.entity_id,
                        entity_type: entity.entity_type,
                        display_name: entity.mention,
                        attributes: {},
                    } as GenerationEntity,
                ]),
        ).values(),
    ].sort((left, right) => left.entity_id.localeCompare(right.entity_id));
    const planningUnavailable = cyclesResult.status === "rejected";

    return (
        <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-100">
            <div className="mx-auto max-w-7xl">
                <header className="flex flex-wrap items-start justify-between gap-5">
                    <div>
                        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
                            Risk and planning
                        </p>
                        <h1 className="mt-2 text-3xl font-bold">
                            Contingency planning console
                        </h1>
                        <p className="mt-2 max-w-3xl text-sm text-slate-400">
                            Generate client-validated risk scenarios, compare
                            authoritative simulation results, and record a human
                            decision. Approval here does not execute operational
                            changes.
                        </p>
                    </div>
                    <span
                        className={`rounded-full border px-3 py-2 text-sm ${connection.status === "ok" ? "border-emerald-800 bg-emerald-950 text-emerald-300" : "border-red-800 bg-red-950 text-red-300"}`}
                    >
                        {connection.status === "ok"
                            ? "Client ready"
                            : "Client unavailable"}
                    </span>
                </header>
                <section className="my-6 grid gap-3 lg:grid-cols-2">
                    <div className="rounded-xl border border-sky-900 bg-sky-950/30 p-4">
                        <h2 className="text-sm font-semibold text-sky-300">
                            You control here
                        </h2>
                        <p className="mt-1 text-xs leading-5 text-slate-300">
                            Risk generation, scenario selection, the baseline
                            simulation request, plan evaluation, deterministic
                            ranking, approval, and rejection. Baseline results
                            flow directly to planning without another form.
                        </p>
                    </div>
                    <div className="rounded-xl border border-violet-900 bg-violet-950/30 p-4">
                        <h2 className="text-sm font-semibold text-violet-300">
                            You control in your connected system
                        </h2>
                        <p className="mt-1 text-xs leading-5 text-slate-300">
                            Operational data, entity IDs, disruption and
                            intervention capabilities, validation rules,
                            simulator logic, authoritative metrics, credentials,
                            and execution of approved interventions.
                        </p>
                    </div>
                </section>
                <section className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {[
                        ["Client", connection.client_id],
                        ["Context", connection.context_version],
                        ["State", connection.state_version],
                        ["Capabilities", connection.capability_version],
                    ].map(([label, value]) => (
                        <div
                            key={label}
                            className="rounded-xl border border-slate-800 bg-slate-900 p-3"
                        >
                            <p className="text-xs text-slate-500">{label}</p>
                            <p className="mt-1 truncate font-mono text-xs text-slate-300">
                                {value ?? "Unavailable"}
                            </p>
                        </div>
                    ))}
                </section>
                {planningUnavailable ? (
                    <div
                        role="alert"
                        className="rounded-xl border border-red-800 bg-red-950 p-5 text-red-300"
                    >
                        <h2 className="font-semibold">
                            Planning service unavailable
                        </h2>
                        <p className="mt-1 text-sm">
                            The console could not load workflow history. Check
                            the platform API and retry this page.
                        </p>
                    </div>
                ) : (
                    <PlanningConsole
                        initialCycles={cycles}
                        entityScope={entityScope}
                        connected={connection.status === "ok"}
                    />
                )}
            </div>
        </main>
    );
}
