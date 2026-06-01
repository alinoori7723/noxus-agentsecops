import type { TimelineStep } from "../types/noxus";
import { SectionHeader } from "./Section";
import { StatusChip } from "./StatusChip";

export function AuditTimeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <section>
      <SectionHeader
        kicker="Audit timeline"
        title="Six-step readiness flow"
        copy="Each card is built only from real report fields: baseline, findings, structured patch proposal, deterministic application, retest, and final readiness."
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {steps.map((s) => (
          <div key={s.step} className="nx-card flex flex-col p-4">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/15 text-xs font-black text-accent-soft">
                {s.step}
              </span>
              <StatusChip label={s.status} color={s.status_color} />
            </div>
            <h3 className="mt-3 text-sm font-extrabold leading-snug text-white">
              {s.label}
            </h3>
            <p className="mt-1.5 flex-1 text-xs leading-relaxed text-slate-400">
              {s.description}
            </p>
            <div className="mt-3 border-t border-line-soft pt-2.5 text-[11px] text-slate-500">
              <span className="font-bold text-slate-300">{s.evidence_count}</span>{" "}
              evidence items
              <div className="mt-0.5">{s.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
