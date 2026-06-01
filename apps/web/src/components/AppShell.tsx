import type { ReactNode } from "react";
import { ShieldCheck, FlaskConical, GitBranch, FileJson, Layers } from "lucide-react";
import type { ProofIndicators } from "../types/noxus";

interface AppShellProps {
  proof: ProofIndicators | null;
  online: boolean | null;
  children: ReactNode;
}

function ProofChip({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-ink-850/80 px-3 py-1 text-xs font-semibold text-slate-300">
      <span className="text-accent-soft">{icon}</span>
      {label}
    </span>
  );
}

export function AppShell({ proof, online, children }: AppShellProps) {
  const testCount = proof?.test_count ?? null;
  const maxIter = proof?.max_tuning_iterations ?? 2;
  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-30 border-b border-line bg-ink-950/85 backdrop-blur">
        <div className="mx-auto flex max-w-[1680px] flex-wrap items-center gap-x-6 gap-y-3 px-6 py-3.5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-accent/40 bg-accent/15 text-accent-soft">
              <ShieldCheck size={20} strokeWidth={2.2} />
            </div>
            <div className="leading-tight">
              <div className="text-[15px] font-extrabold tracking-tight text-white">
                Noxus AgentSecOps
              </div>
              <div className="text-[11px] font-medium text-slate-400">
                Pre-production readiness tester
              </div>
            </div>
          </div>

          <div className="ml-auto hidden flex-wrap items-center gap-2 lg:flex">
            {testCount !== null && (
              <ProofChip
                icon={<FlaskConical size={14} />}
                label={`${testCount} tests passing`}
              />
            )}
            <ProofChip
              icon={<Layers size={14} />}
              label={`MAX_TUNING_ITERATIONS = ${maxIter}`}
            />
            <ProofChip icon={<ShieldCheck size={14} />} label="Schema-bound agents" />
            <ProofChip
              icon={<GitBranch size={14} />}
              label="Deterministic patch engine"
            />
            <ProofChip icon={<FileJson size={14} />} label="Local JSONL audit" />
          </div>

          <span
            className="inline-flex items-center gap-1.5 rounded-full border border-line bg-ink-850 px-2.5 py-1 text-[11px] font-semibold text-slate-400"
            title={online ? "API reachable" : "API status"}
          >
            <span
              className={
                "h-1.5 w-1.5 rounded-full " +
                (online === null
                  ? "bg-slate-500"
                  : online
                    ? "bg-emerald-400"
                    : "bg-rose-400")
              }
            />
            {online === null ? "checking" : online ? "API online" : "API offline"}
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-[1680px] px-6 py-8">{children}</main>

      <footer className="mx-auto max-w-[1680px] px-6 pb-10 pt-4">
        <p className="text-xs leading-relaxed text-slate-500">
          Local demo presentation. Noxus AgentSecOps is a pre-production readiness
          tester — not a runtime firewall, DLP replacement, or compliance
          certification engine. No production traffic is intercepted.
        </p>
      </footer>
    </div>
  );
}
