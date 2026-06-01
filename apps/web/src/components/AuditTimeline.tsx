import type { TimelineStep } from "../types/noxus";
import { SectionHeader } from "./Section";
import { StatusChip } from "./StatusChip";

export function AuditTimeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <div className="card p-5">
      <SectionHeader
        kicker="Audit timeline"
        title="Six-step readiness flow"
        copy="Each step is built only from real report fields — baseline, findings, structured patch proposal, deterministic application, retest, and final readiness."
      />
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {steps.map((s) => (
          <li
            key={s.step}
            className="flex flex-col rounded-lg border border-slate-200 bg-slate-50/60 p-3.5"
          >
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-600 text-[11px] font-bold text-white">
                {s.step}
              </span>
              <StatusChip label={s.status} color={s.status_color} />
            </div>
            <h4 className="mt-2.5 text-[13px] font-bold leading-snug text-slate-900">
              {s.label}
            </h4>
            <p className="mt-1 flex-1 text-[11.5px] leading-relaxed text-slate-500">
              {s.description}
            </p>
            <div className="mt-2.5 border-t border-slate-200 pt-2 text-[11px] text-slate-500">
              <span className="font-bold text-slate-700">{s.evidence_count}</span>{" "}
              evidence items
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
