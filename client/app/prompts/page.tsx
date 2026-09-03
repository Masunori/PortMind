import PromptEditor from "@/components/PromptEditor";
import { getAgentPrompts } from "@/lib/api";

export default async function PromptsPage() {
    const prompts = await getAgentPrompts();
    return (
        <main className="min-h-screen bg-[radial-gradient(circle_at_top_right,rgba(14,165,233,0.09),transparent_32rem)] px-6 py-12 text-slate-100">
            <div className="mx-auto max-w-6xl">
                <header><p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">Agent configuration</p>
                    <h1 className="mt-2 text-4xl font-bold tracking-tight">System prompts</h1>
                    <p className="mt-3 max-w-2xl leading-7 text-slate-400">Tune how each agent reasons about evidence and plans. Prompt contracts and output validation continue to protect the workflow.</p>
                </header>
                <PromptEditor initialPrompts={prompts} />
            </div>
        </main>
    );
}
