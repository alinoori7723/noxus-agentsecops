import type { ReactNode } from "react";
import { FlaskConical, Layers, Container, Beaker } from "lucide-react";
import type { ProofIndicators } from "../types/noxus";

interface TopHeaderProps {
  title: string;
  subtitle: string;
  proof: ProofIndicators | null;
  online: boolean | null;
}

function Chip({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600">
      <span className="text-brand-600">{icon}</span>
      {children}
    </span>
  );
}

export function TopHeader({ title, subtitle, proof, online }: TopHeaderProps) {
  const pyTests = proof?.test_count ?? 457;
  const maxIter = proof?.max_tuning_iterations ?? 2;
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-6 py-3.5 lg:px-8">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-extrabold tracking-tight text-slate-900">
            {title}
          </h1>
          <p className="truncate text-[13px] text-slate-500">{subtitle}</p>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <span className="hidden items-center gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700 sm:inline-flex">
            <span
              className={
                "h-1.5 w-1.5 rounded-full " +
                (online ? "bg-emerald-500" : online === false ? "bg-rose-500" : "bg-slate-400")
              }
            />
            Local Demo
          </span>
          <Chip icon={<FlaskConical size={13} />}>{pyTests} Python tests</Chip>
          <Chip icon={<Beaker size={13} />}>55 frontend tests</Chip>
          <Chip icon={<Layers size={13} />}>MAX_TUNING_ITERATIONS = {maxIter}</Chip>
          <Chip icon={<Container size={13} />}>Docker-ready</Chip>
        </div>
      </div>
    </header>
  );
}
