"use client";

import Link from "next/link";
import { FormEvent, ReactNode, useState } from "react";
import LoadingButton from "@/components/LoadingButton";
import SupplyChainGraph from "@/components/SupplyChainGraph";
import type { ChangeImpact, EntityKind, EntitySchema, FieldDefinition, SimulationRule } from "@/types/extensibility";
import type { Edge, Network, Node } from "@/types/network";

type Tab = "graph" | "nodes" | "edges" | "schemas" | "rules";

const inputClass = "w-full rounded-xl border border-slate-700/80 bg-slate-950/80 px-3.5 py-2.5 text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20";
const buttonClass = "w-full rounded-xl bg-sky-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-sky-950/30 transition hover:bg-sky-500";
const panelClass = "rounded-2xl border border-slate-800 bg-slate-900/70 shadow-xl shadow-black/10 backdrop-blur";

const tabLabels: Record<Tab, string> = {
    graph: "Overview",
    nodes: "Nodes",
    edges: "Routes",
    schemas: "Schemas",
    rules: "Simulation rules",
};

function apiUrl(): string {
    return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${apiUrl()}${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", ...init?.headers },
    });
    if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { detail?: string };
        throw new Error(body.detail ?? `Request failed (${response.status})`);
    }
    return response.status === 204 ? undefined as T : await response.json() as T;
}

function parseAttributes(value: FormDataEntryValue | null): Record<string, unknown> {
    const parsed = JSON.parse(String(value || "{}")) as unknown;
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("Attributes must be a JSON object");
    }
    return parsed as Record<string, unknown>;
}

export default function NetworkManager({
    initialNetwork,
    initialSchemas,
    initialRules,
}: {
    initialNetwork: Network;
    initialSchemas: EntitySchema[];
    initialRules: SimulationRule[];
}) {
    const [tab, setTab] = useState<Tab>("graph");
    const [network, setNetwork] = useState(initialNetwork);
    const [schemas, setSchemas] = useState(initialSchemas);
    const [rules, setRules] = useState(initialRules);
    const [pending, setPending] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    async function execute(key: string, work: () => Promise<void>) {
        setPending(key);
        setMessage(null);
        try {
            await work();
            setMessage("Saved. The live network and AI context are now current.");
        } catch (error) {
            setMessage(error instanceof Error ? error.message : "Request failed");
        } finally {
            setPending(null);
        }
    }

    async function addNode(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        await execute("add-node", async () => {
            const node = await request<Node>("/api/nodes", { method: "POST", body: JSON.stringify({
                id: form.get("id"), name: form.get("name"), type: form.get("type"),
                inventory: Number(form.get("inventory")), capacity: Number(form.get("capacity")),
                schema_version_id: form.get("schema") || null, attributes: parseAttributes(form.get("attributes")),
            }) });
            setNetwork((current) => ({ ...current, nodes: [...current.nodes, node] }));
            event.currentTarget.reset();
        });
    }

    async function addEdge(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        await execute("add-edge", async () => {
            const edge = await request<Edge>("/api/edges", { method: "POST", body: JSON.stringify({
                id: form.get("id"), source_id: form.get("source"), target_id: form.get("target"), mode: form.get("mode"),
                transit_time_hours: Number(form.get("time")), cost: Number(form.get("cost")), capacity: Number(form.get("capacity")),
                schema_version_id: form.get("schema") || null, attributes: parseAttributes(form.get("attributes")),
            }) });
            setNetwork((current) => ({ ...current, edges: [...current.edges, edge] }));
            event.currentTarget.reset();
        });
    }

    async function remove(kind: "nodes" | "edges", id: string) {
        await execute(`delete-${id}`, async () => {
            const impact = await request<ChangeImpact>(`/api/${kind}/${id}/delete-impact`);
            const summary = `${impact.edge_count} edges, ${impact.shipment_count} shipments, ${impact.disruption_count} disruptions affected.`;
            if (!window.confirm(`${summary}\n\nDelete ${id}?`)) return;
            await request<void>(`/api/${kind}/${id}`, { method: "DELETE" });
            setNetwork((current) => ({
                nodes: kind === "nodes" ? current.nodes.filter((item) => item.id !== id) : current.nodes,
                edges: kind === "edges" ? current.edges.filter((item) => item.id !== id) : current.edges,
            }));
        });
    }

    async function editNode(node: Node) {
        const name = window.prompt("Node name", node.name);
        if (!name) return;
        const attributes = window.prompt("Custom attributes JSON", JSON.stringify(node.attributes));
        if (attributes === null) return;
        await execute(`edit-${node.id}`, async () => {
            const updated = await request<Node>(`/api/nodes/${node.id}`, { method: "PATCH", body: JSON.stringify({ name, attributes: JSON.parse(attributes) as Record<string, unknown> }) });
            setNetwork((current) => ({ ...current, nodes: current.nodes.map((item) => item.id === updated.id ? updated : item) }));
        });
    }

    async function editEdge(edge: Edge) {
        const mode = window.prompt("Transport mode", edge.mode);
        if (!mode) return;
        const attributes = window.prompt("Custom attributes JSON", JSON.stringify(edge.attributes));
        if (attributes === null) return;
        await execute(`edit-${edge.id}`, async () => {
            const updated = await request<Edge>(`/api/edges/${edge.id}`, { method: "PATCH", body: JSON.stringify({ mode, attributes: JSON.parse(attributes) as Record<string, unknown> }) });
            setNetwork((current) => ({ ...current, edges: current.edges.map((item) => item.id === updated.id ? updated : item) }));
        });
    }

    async function addSchema(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        await execute("add-schema", async () => {
            const fields = JSON.parse(String(form.get("fields") || "[]")) as FieldDefinition[];
            const created = await request<EntitySchema>("/api/schemas", { method: "POST", body: JSON.stringify({
                id: form.get("id"), name: form.get("name"), entity_kind: form.get("kind") as EntityKind, fields,
            }) });
            setSchemas((current) => [...current, created]);
            event.currentTarget.reset();
        });
    }

    async function versionSchema(item: EntitySchema) {
        const value = window.prompt("New immutable fields JSON", JSON.stringify(item.fields, null, 2));
        if (!value) return;
        await execute(`version-${item.id}`, async () => {
            const fields = JSON.parse(value) as FieldDefinition[];
            const impact = await request<ChangeImpact>(`/api/schemas/${item.id}/versions/preview`, { method: "POST", body: JSON.stringify({ fields }) });
            if (!window.confirm(`${impact.entity_count} entities and ${impact.rule_count} related rules are affected. A new immutable version will be created. Apply?`)) return;
            const updated = await request<EntitySchema>(`/api/schemas/${item.id}/versions`, { method: "POST", body: JSON.stringify({ fields }) });
            setSchemas((current) => current.map((schema) => schema.id === updated.id ? updated : schema));
        });
    }

    async function addRule(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        await execute("add-rule", async () => {
            const created = await request<SimulationRule>("/api/simulation-rules", { method: "POST", body: JSON.stringify({
                id: form.get("id"), name: form.get("name"), trigger: "EDGE_TRAVERSED", operation: form.get("operation"),
                source: form.get("source"), target_metric: form.get("target"), enabled: true,
            }) });
            setRules((current) => [...current, created]);
            event.currentTarget.reset();
        });
    }

    const tabs: Tab[] = ["graph", "nodes", "edges", "schemas", "rules"];
    const nodeSchemas = schemas.filter((item) => item.entity_kind === "NODE");
    const edgeSchemas = schemas.filter((item) => item.entity_kind === "EDGE");

    return (
        <div className="mx-auto max-w-[1500px]">
            <header className={`${panelClass} relative overflow-hidden p-6 sm:p-8`}>
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400 to-transparent" />
                <div className="absolute -right-24 -top-24 h-64 w-64 rounded-full bg-sky-500/10 blur-3xl" />
                <div className="relative flex flex-wrap items-start justify-between gap-6">
                    <div>
                        <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.22em] text-emerald-400">
                            <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.8)]" />
                            Live digital twin
                        </div>
                        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Network management</h1>
                        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">Shape the operational graph, extend its data model, and configure deterministic simulation behavior.</p>
                    </div>
                    <Link href="/" className="group inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-950/60 px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:border-sky-700 hover:text-white">
                        <span aria-hidden="true" className="transition group-hover:-translate-x-0.5">←</span>
                        Dashboard
                    </Link>
                </div>
                <dl className="relative mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <Stat label="Nodes" value={network.nodes.length} accent="text-sky-300" />
                    <Stat label="Routes" value={network.edges.length} accent="text-cyan-300" />
                    <Stat label="Schemas" value={schemas.length} accent="text-emerald-300" />
                    <Stat label="Rules" value={rules.length} accent="text-violet-300" />
                </dl>
            </header>

            <nav aria-label="Network management sections" className="my-6 overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900/70 p-1.5">
                <div className="flex min-w-max gap-1">
                    {tabs.map((item) => (
                        <button key={item} type="button" onClick={() => setTab(item)} aria-current={tab === item ? "page" : undefined} className={`rounded-xl px-4 py-2.5 text-sm font-medium transition ${tab === item ? "bg-sky-600 text-white shadow-lg shadow-sky-950/40" : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"}`}>
                            {tabLabels[item]}
                        </button>
                    ))}
                </div>
            </nav>

            {message && (
                <div role="status" className={`mb-6 flex items-center gap-3 rounded-xl border px-4 py-3 text-sm ${message.startsWith("Saved") ? "border-emerald-800/80 bg-emerald-950/30 text-emerald-300" : "border-red-800/80 bg-red-950/30 text-red-300"}`}>
                    <span className={`h-2 w-2 shrink-0 rounded-full ${message.startsWith("Saved") ? "bg-emerald-400" : "bg-red-400"}`} />
                    {message}
                </div>
            )}

            {tab === "graph" && (
                <section className="grid gap-6 xl:grid-cols-[minmax(0,2.2fr)_minmax(290px,0.8fr)]">
                    <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70 shadow-xl shadow-black/10">
                        <div className="border-b border-slate-800 px-5 py-4"><h2 className="font-semibold">Network topology</h2><p className="mt-1 text-xs text-slate-500">Current persisted nodes and transport links</p></div>
                        <SupplyChainGraph network={network} disruptions={[]} exposures={[]} />
                    </div>
                    <div className="space-y-5">
                        <SummaryList title="Network nodes" count={network.nodes.length} items={network.nodes.map((node) => ({ primary: node.name, secondary: `${node.type} · ${node.id}` }))} />
                        <SummaryList title="Transport routes" count={network.edges.length} items={network.edges.map((edge) => ({ primary: `${edge.source_id} → ${edge.target_id}`, secondary: `${edge.mode} · ${edge.transit_time_hours}h` }))} />
                    </div>
                </section>
            )}

            {tab === "nodes" && (
                <Workspace title="Nodes" description="Physical and operational locations in the supply-chain graph." form={<EntityForm title="Add node" onSubmit={addNode} pending={pending === "add-node"} schemas={nodeSchemas} />}>
                    {network.nodes.map((node) => <EntityCard key={node.id} title={node.name} identifier={node.id} badge={node.type} metadata={[`Inventory ${node.inventory.toLocaleString()}`, `Capacity ${node.capacity.toLocaleString()}`, node.schema_version_id ?? "Core fields only"]} attributes={node.attributes} editPending={pending === `edit-${node.id}`} deletePending={pending === `delete-${node.id}`} onEdit={() => editNode(node)} onDelete={() => remove("nodes", node.id)} />)}
                </Workspace>
            )}

            {tab === "edges" && (
                <Workspace title="Routes" description="Directed transport connections between network nodes." form={<EdgeForm onSubmit={addEdge} pending={pending === "add-edge"} schemas={edgeSchemas} nodes={network.nodes} />}>
                    {network.edges.map((edge) => <EntityCard key={edge.id} title={`${edge.source_id} → ${edge.target_id}`} identifier={edge.id} badge={edge.mode} metadata={[`${edge.transit_time_hours} hours`, `$${edge.cost.toLocaleString()}`, `Capacity ${edge.capacity.toLocaleString()}`]} attributes={edge.attributes} editPending={pending === `edit-${edge.id}`} deletePending={pending === `delete-${edge.id}`} onEdit={() => editEdge(edge)} onDelete={() => remove("edges", edge.id)} />)}
                </Workspace>
            )}

            {tab === "schemas" && (
                <Workspace title="Schemas" description="Versioned, typed extensions to the core network model." form={<SchemaForm onSubmit={addSchema} pending={pending === "add-schema"} />}>
                    {schemas.map((item) => (
                        <article key={item.id} className={`${panelClass} overflow-hidden transition hover:border-slate-700`}>
                            <div className="flex flex-wrap items-start justify-between gap-4 p-5"><div><div className="flex items-center gap-2"><h3 className="font-semibold text-slate-100">{item.name}</h3><Badge>{item.entity_kind}</Badge><Badge>v{item.version}</Badge></div><p className="mt-1 font-mono text-xs text-slate-500">{item.id}</p></div><LoadingButton pending={pending === `version-${item.id}`} pendingLabel="Validating…" onClick={() => versionSchema(item)} className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-sky-700 hover:text-sky-300">New version</LoadingButton></div>
                            <div className="border-t border-slate-800 bg-slate-950/40 px-5 py-4">{item.fields.length === 0 ? <p className="text-sm text-slate-500">No custom fields</p> : <div className="flex flex-wrap gap-2">{item.fields.map((field) => <span key={field.key} className="rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1.5 font-mono text-xs text-slate-300">{field.key} <span className="text-emerald-400">{field.type.toLowerCase()}</span></span>)}</div>}</div>
                        </article>
                    ))}
                </Workspace>
            )}

            {tab === "rules" && (
                <Workspace title="Simulation rules" description="Auditable, declarative updates executed at safe lifecycle hooks." form={<RuleForm onSubmit={addRule} pending={pending === "add-rule"} />}>
                    {rules.map((rule) => (
                        <article key={rule.id} className={`${panelClass} p-5 transition hover:border-slate-700`}>
                            <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold text-slate-100">{rule.name}</h3><p className="mt-1 font-mono text-xs text-slate-500">{rule.id}</p></div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${rule.enabled ? "bg-emerald-950 text-emerald-300" : "bg-slate-800 text-slate-400"}`}>{rule.enabled ? "Enabled" : "Disabled"}</span></div>
                            <div className="mt-4 flex flex-wrap items-center gap-2 text-xs"><Badge>{rule.trigger}</Badge><span className="text-slate-500">then</span><code className="rounded bg-slate-950 px-2 py-1 text-sky-300">{rule.target_metric}</code><Badge>{rule.operation}</Badge><code className="rounded bg-slate-950 px-2 py-1 text-emerald-300">{rule.source}</code></div>
                        </article>
                    ))}
                </Workspace>
            )}
        </div>
    );
}

function Stat({ label, value, accent }: { label: string; value: number; accent: string }) {
    return (
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 px-4 py-3">
            <dt className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</dt>
            <dd className={`mt-1 text-2xl font-bold ${accent}`}>{value}</dd>
        </div>
    );
}

function Badge({ children }: { children: ReactNode }) {
    return <span className="rounded-full border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-300">{children}</span>;
}

function SummaryList({ title, count, items }: { title: string; count: number; items: { primary: string; secondary: string }[] }) {
    return (
        <article className={`${panelClass} overflow-hidden`}>
            <header className="flex items-center justify-between border-b border-slate-800 px-5 py-4"><h2 className="font-semibold">{title}</h2><Badge>{count}</Badge></header>
            <div className="max-h-72 divide-y divide-slate-800/80 overflow-y-auto">
                {items.map((item, index) => <div key={`${item.primary}-${index}`} className="px-5 py-3 transition hover:bg-slate-800/30"><p className="truncate text-sm font-medium text-slate-200">{item.primary}</p><p className="mt-1 truncate text-xs text-slate-500">{item.secondary}</p></div>)}
            </div>
        </article>
    );
}

function Workspace({ title, description, form, children }: { title: string; description: string; form: ReactNode; children: ReactNode }) {
    return (
        <section>
            <div className="mb-5"><h2 className="text-xl font-semibold">{title}</h2><p className="mt-1 text-sm text-slate-500">{description}</p></div>
            <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
                <div className="space-y-3">{children}</div>
                <aside className="xl:sticky xl:top-6">{form}</aside>
            </div>
        </section>
    );
}

function EntityCard({ title, identifier, badge, metadata, attributes, editPending, deletePending, onEdit, onDelete }: { title: string; identifier: string; badge: string; metadata: string[]; attributes: Record<string, unknown>; editPending: boolean; deletePending: boolean; onEdit: () => void; onDelete: () => void }) {
    return (
        <article className={`${panelClass} p-5 transition hover:border-slate-700 hover:bg-slate-900`}>
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold text-slate-100">{title}</h3><Badge>{badge}</Badge></div><p className="mt-1 truncate font-mono text-xs text-slate-500">{identifier}</p></div>
                <div className="flex gap-2"><LoadingButton pending={editPending} pendingLabel="Saving…" onClick={onEdit} className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-sky-700 hover:text-sky-300">Edit</LoadingButton><LoadingButton pending={deletePending} pendingLabel="Checking…" onClick={onDelete} className="rounded-lg border border-red-900/80 bg-red-950/50 px-3 py-2 text-xs font-medium text-red-300 transition hover:bg-red-900/60">Delete</LoadingButton></div>
            </div>
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-slate-800 pt-4 text-xs text-slate-400">{metadata.map((item) => <span key={item}>{item}</span>)}</div>
            {Object.keys(attributes).length > 0 && <div className="mt-3 flex flex-wrap gap-2">{Object.entries(attributes).map(([key, value]) => <span key={key} className="rounded-lg bg-slate-950 px-2.5 py-1.5 font-mono text-xs text-slate-400"><span className="text-emerald-400">{key}</span>: {String(value)}</span>)}</div>}
        </article>
    );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
    return <label className="block"><span className="mb-1.5 block text-xs font-semibold text-slate-300">{label}</span>{children}{hint && <span className="mt-1.5 block text-xs leading-5 text-slate-600">{hint}</span>}</label>;
}

function FormShell({ title, description, children }: { title: string; description: string; children: ReactNode }) {
    return <div className={`${panelClass} overflow-hidden`}><header className="border-b border-slate-800 px-5 py-4"><h2 className="font-semibold">{title}</h2><p className="mt-1 text-xs leading-5 text-slate-500">{description}</p></header><div className="space-y-4 p-5">{children}</div></div>;
}

function EntityForm({ title, onSubmit, pending, schemas }: { title: string; onSubmit: (event: FormEvent<HTMLFormElement>) => void; pending: boolean; schemas: EntitySchema[] }) {
    return (
        <form onSubmit={onSubmit}><FormShell title={title} description="Create a validated location in the live graph.">
            <Field label="Identifier" hint="Stable ID; cannot be changed later."><input required name="id" placeholder="hai-phong-port" className={inputClass} /></Field>
            <Field label="Display name"><input required name="name" placeholder="Hai Phong Port" className={inputClass} /></Field>
            <div className="grid grid-cols-2 gap-3"><Field label="Type"><input required name="type" placeholder="port" className={inputClass} /></Field><Field label="Schema"><select name="schema" className={inputClass}><option value="">Core only</option>{schemas.map((schema) => <option key={schema.id} value={schema.current_version_id}>{schema.name} v{schema.version}</option>)}</select></Field></div>
            <div className="grid grid-cols-2 gap-3"><Field label="Inventory"><input required name="inventory" type="number" min="0" placeholder="0" className={inputClass} /></Field><Field label="Capacity"><input required name="capacity" type="number" min="0" placeholder="1000" className={inputClass} /></Field></div>
            <Field label="Custom attributes" hint="JSON matching the selected schema version."><textarea name="attributes" rows={4} defaultValue="{}" spellCheck={false} className={`${inputClass} resize-y font-mono text-xs`} /></Field>
            <LoadingButton pending={pending} pendingLabel="Adding node…" className={buttonClass}>Add node</LoadingButton>
        </FormShell></form>
    );
}

function EdgeForm({ onSubmit, pending, schemas, nodes }: { onSubmit: (event: FormEvent<HTMLFormElement>) => void; pending: boolean; schemas: EntitySchema[]; nodes: Node[] }) {
    return (
        <form onSubmit={onSubmit}><FormShell title="Add route" description="Connect two distinct nodes with a directed transport edge.">
            <Field label="Identifier"><input required name="id" placeholder="hph-to-sin" className={inputClass} /></Field>
            <div className="grid grid-cols-2 gap-3">{["source", "target"].map((name) => <Field key={name} label={name === "source" ? "Origin" : "Destination"}><select required name={name} className={inputClass}><option value="">Select</option>{nodes.map((node) => <option key={node.id} value={node.id}>{node.name}</option>)}</select></Field>)}</div>
            <div className="grid grid-cols-2 gap-3"><Field label="Mode"><input required name="mode" placeholder="sea" className={inputClass} /></Field><Field label="Schema"><select name="schema" className={inputClass}><option value="">Core only</option>{schemas.map((schema) => <option key={schema.id} value={schema.current_version_id}>{schema.name} v{schema.version}</option>)}</select></Field></div>
            <div className="grid grid-cols-3 gap-3"><Field label="Hours"><input required name="time" type="number" min="0.01" step="any" placeholder="12" className={inputClass} /></Field><Field label="Cost"><input required name="cost" type="number" min="0" step="any" placeholder="2400" className={inputClass} /></Field><Field label="Capacity"><input required name="capacity" type="number" min="0" step="any" placeholder="1000" className={inputClass} /></Field></div>
            <Field label="Custom attributes" hint="JSON matching the selected route schema."><textarea name="attributes" rows={4} defaultValue="{}" spellCheck={false} className={`${inputClass} resize-y font-mono text-xs`} /></Field>
            <LoadingButton pending={pending} pendingLabel="Adding route…" className={buttonClass}>Add route</LoadingButton>
        </FormShell></form>
    );
}

function SchemaForm({ onSubmit, pending }: { onSubmit: (event: FormEvent<HTMLFormElement>) => void; pending: boolean }) {
    return (
        <form onSubmit={onSubmit}><FormShell title="Create schema" description="Publish an immutable first version with typed fields.">
            <Field label="Identifier"><input required name="id" placeholder="sea-route" className={inputClass} /></Field>
            <Field label="Display name"><input required name="name" placeholder="Sea Route" className={inputClass} /></Field>
            <Field label="Entity kind"><select name="kind" className={inputClass}><option value="NODE">Node</option><option value="EDGE">Edge</option></select></Field>
            <Field label="Field definitions" hint="Safe typed JSON only; executable expressions are rejected."><textarea name="fields" rows={12} spellCheck={false} defaultValue={'[{\n  "key": "carbon_kg",\n  "label": "Carbon",\n  "type": "NUMBER",\n  "required": true,\n  "default": 0,\n  "unit": "kg",\n  "enum_values": [],\n  "behavior": "FLOW"\n}]'} className={`${inputClass} resize-y font-mono text-xs leading-5`} /></Field>
            <LoadingButton pending={pending} pendingLabel="Creating schema…" className={buttonClass}>Create immutable v1</LoadingButton>
        </FormShell></form>
    );
}

function RuleForm({ onSubmit, pending }: { onSubmit: (event: FormEvent<HTMLFormElement>) => void; pending: boolean }) {
    return (
        <form onSubmit={onSubmit}><FormShell title="Add safe rule" description="Build deterministic behavior from a fixed operation vocabulary.">
            <Field label="Identifier"><input required name="id" placeholder="accumulate-carbon" className={inputClass} /></Field>
            <Field label="Rule name"><input required name="name" placeholder="Accumulate route carbon" className={inputClass} /></Field>
            <Field label="Lifecycle hook"><div className="rounded-xl border border-slate-800 bg-slate-950/60 px-3.5 py-2.5 font-mono text-xs text-emerald-300">EDGE_TRAVERSED</div></Field>
            <Field label="Operation"><select name="operation" className={inputClass}>{["SET", "ADD", "SUBTRACT", "MULTIPLY", "MIN", "MAX"].map((value) => <option key={value}>{value}</option>)}</select></Field>
            <Field label="Numeric source"><input required name="source" placeholder="edge.attributes.carbon_kg" className={inputClass} /></Field>
            <Field label="Result metric"><input required name="target" placeholder="total_carbon_kg" className={inputClass} /></Field>
            <LoadingButton pending={pending} pendingLabel="Validating rule…" className={buttonClass}>Validate and add</LoadingButton>
        </FormShell></form>
    );
}
