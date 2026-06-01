import { Target, Wrench, RefreshCw } from "lucide-react";
import { SectionHeader } from "./Section";

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

export function EmptyState() {
  return (
    <section>
      <SectionHeader
        kicker="Ready to run"
        title="The cockpit fills with real data after an assessment"
        copy="Nothing below is prefilled or synthesized. Run an assessment to generate a local report — these three steps run in order."
      />
      <div className="nx-panel p-6">
        <div className="mb-5 text-sm text-slate-400">
          No report generated yet. Deterministic Mode needs no credentials and is
          fully reproducible.
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            return (
              <div key={s.title} className="nx-card p-5">
                <div className="flex items-center gap-2.5">
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/15 text-sm font-black text-accent-soft">
                    {i + 1}
                  </span>
                  <Icon size={18} className="text-slate-400" />
                </div>
                <h3 className="mt-3 text-sm font-extrabold text-white">{s.title}</h3>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
                  {s.copy}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
