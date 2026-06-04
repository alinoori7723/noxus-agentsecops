import {
  Swords,
  Wrench,
  FileText,
  ArrowRight,
  ShieldAlert,
  Play,
  SlidersHorizontal,
} from "lucide-react";

interface OverviewProps {
  onConfigure: () => void;
  onRunDemo: () => void;
  running: boolean;
}

const VALUE_CARDS = [
  {
    icon: Swords,
    title: "Red Team Probes",
    copy: "Structured adversarial probes — injection, PII, secret and identifier leakage, proprietary-context exposure — with evidence.",
  },
  {
    icon: Wrench,
    title: "Deterministic Patching",
    copy: "Agents propose schema-bound changes; a deterministic engine applies only the allowed ones. No silent prompt edits.",
  },
  {
    icon: FileText,
    title: "Evidence Report",
    copy: "Before/after scores, honest detection labels, open risks, and a CONDITIONAL_PASS verdict you can defend in review.",
  },
];

const FLOW = ["Probe", "Evaluate", "Patch", "Retest", "Report"];

export function Overview({ onConfigure, onRunDemo, running }: OverviewProps) {
  return (
    <div className="space-y-6">
      <section className="card p-6 lg:p-8">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-[11px] font-bold uppercase tracking-wide text-brand-700">
          Red Team / Blue Team readiness loop
        </span>
        <h2 className="mt-4 text-3xl font-black tracking-tight text-slate-900">
          Noxus AgentSecOps
        </h2>
        <p className="mt-3 max-w-2xl text-base leading-relaxed text-slate-600">
          Pre-production AI security readiness testing for enterprise LLM apps.
        </p>
        <p className="mt-2 flex items-start gap-2 text-sm leading-relaxed text-slate-500">
          <ShieldAlert size={16} className="mt-0.5 shrink-0 text-amber-500" />
          <span>
            Not a runtime firewall. Not a certification engine. Not full
            autonomous remediation. A bounded agentic audit and
            remediation-readiness loop: it applies only deterministic allowed
            patches and refuses to mark the target safe when risks remain.
          </span>
        </p>

        <div className="mt-6 flex flex-wrap gap-3">
          <button type="button" onClick={onConfigure} className="btn-primary">
            <SlidersHorizontal size={16} /> Configure Assessment
          </button>
          <button
            type="button"
            onClick={onRunDemo}
            disabled={running}
            className="btn-ghost"
          >
            <Play size={16} /> Run Deterministic Demo
          </button>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        {VALUE_CARDS.map((c) => {
          const Icon = c.icon;
          return (
            <div key={c.title} className="card p-5">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                <Icon size={20} />
              </div>
              <h3 className="mt-3.5 text-sm font-bold text-slate-900">{c.title}</h3>
              <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500">
                {c.copy}
              </p>
            </div>
          );
        })}
      </div>

      <section className="card p-6">
        <div className="kicker">How it works</div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {FLOW.map((step, i) => (
            <div key={step} className="flex items-center gap-2">
              <span className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2 text-sm font-bold text-slate-800">
                {step}
              </span>
              {i < FLOW.length - 1 && (
                <ArrowRight size={16} className="text-slate-300" />
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
