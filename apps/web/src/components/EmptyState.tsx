import { Target, Wrench, RefreshCw, Play } from "lucide-react";

const STEPS = [
  {
    icon: Target,
    title: "Run baseline probes",
    copy: "Red Team probes run against the original target and capture evidence-backed findings.",
  },
  {
    icon: Wrench,
    title: "Apply structured remediation",
    copy: "Agents propose schema-bound patches; only the deterministic engine applies the allowed changes.",
  },
  {
    icon: RefreshCw,
    title: "Retest and report open risks",
    copy: "Probes rerun against the patched target. Unresolved risk stays visible — CONDITIONAL_PASS, never a fake PASS.",
  },
];

export function EmptyState({ onGoToAssessment }: { onGoToAssessment: () => void }) {
  return (
    <div className="card p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="kicker">Ready to run</div>
          <h3 className="mt-1 text-base font-bold text-slate-900">
            The dashboard fills with real data after an assessment
          </h3>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Nothing below is prefilled or synthesized. Deterministic Mode needs no
            credentials and is fully reproducible.
          </p>
        </div>
        <button type="button" onClick={onGoToAssessment} className="btn-primary">
          <Play size={16} /> Go to Assessment
        </button>
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          return (
            <div key={s.title} className="rounded-lg border border-slate-200 bg-slate-50/60 p-5">
              <div className="flex items-center gap-2.5">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">
                  {i + 1}
                </span>
                <Icon size={17} className="text-slate-400" />
              </div>
              <h4 className="mt-3 text-[13px] font-bold text-slate-900">{s.title}</h4>
              <p className="mt-1 text-[12px] leading-relaxed text-slate-500">
                {s.copy}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
