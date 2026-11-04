import { BookOpenText, Bot, Database, Globe2, ShieldCheck, Workflow } from "lucide-react";

import { Wordmark } from "@/components/shell/logo";

const PILLARS = [
  { icon: Bot, title: "Multi-agent missions", body: "Planner, researchers, analyst and verifier on a LangGraph runtime." },
  { icon: Globe2, title: "Live web research", body: "Real sources retrieved through a hardened, SSRF-safe fetcher." },
  { icon: BookOpenText, title: "Grounded answers", body: "Hybrid RAG with page-level citations you can open and inspect." },
  { icon: Database, title: "Real analysis", body: "DuckDB-computed statistics and charts — never model-invented numbers." },
  { icon: Workflow, title: "Visual workflows", body: "Compose and run typed pipelines with human approval checkpoints." },
  { icon: ShieldCheck, title: "Local first", body: "Runs on your machine with a local model. No paid API required." },
];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-[#0b1530] p-12 text-white lg:flex lg:flex-col">
        <div className="nx-grid absolute inset-0 opacity-40 [mask-image:radial-gradient(ellipse_at_30%_20%,black,transparent_70%)]" />
        <div className="absolute -right-40 -top-40 size-[520px] rounded-full bg-[radial-gradient(circle,rgb(37_99_235/0.55),transparent_65%)]" />
        <div className="absolute -bottom-48 -left-24 size-[460px] rounded-full bg-[radial-gradient(circle,rgb(6_182_212/0.28),transparent_65%)]" />
        <div className="relative">
          <div className="[&_.text-ink]:text-white [&_.text-faint]:text-[#93a4c8]">
            <Wordmark />
          </div>
        </div>
        <div className="relative mt-auto max-w-xl">
          <h2 className="text-[34px] font-semibold leading-[1.15] tracking-[-0.03em]">
            Think, plan, research, analyze, verify — <span className="text-[#7dd3fc]">and create.</span>
          </h2>
          <p className="mt-4 text-[15px] leading-relaxed text-[#b6c3df]">
            An AI workspace where every answer shows its work: the plan, the agents, the tool calls and the evidence
            behind each claim.
          </p>
          <div className="mt-10 grid grid-cols-2 gap-x-8 gap-y-6">
            {PILLARS.map((p) => (
              <div key={p.title} className="flex gap-3">
                <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5">
                  <p.icon className="size-4 text-[#7dd3fc]" />
                </div>
                <div>
                  <div className="text-[13.5px] font-medium">{p.title}</div>
                  <div className="mt-0.5 text-[12.5px] leading-snug text-[#93a4c8]">{p.body}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>
      <main className="flex items-center justify-center bg-bg px-5 py-12">
        <div className="w-full max-w-[400px]">{children}</div>
      </main>
    </div>
  );
}
