import { ShieldAlert, CheckCircle2, XCircle } from "lucide-react";
import type { ReportSummary as Summary } from "../types/noxus";
import { StatusChip } from "./StatusChip";

// Judge-safe top-level summary: separates what the run IMPROVED from what
// remains BLOCKED, and states plainly why the final state is not PASS. It never
// presents the patch count as a success count and never implies a fake PASS.
export function ReportSummary({ model }: { model: Summary }) {
  const improved = model.what_improved;
  const blocked = model.what_remains_blocked;
  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-slate-50/70 px-5 py-3.5">
        <ShieldAlert size={18} className="text-amber-500" />
        <div>
          <div className="kicker">Report summary</div>
          <h3 className="mt-0.5 text-base font-bold text-slate-900">
            Readiness gate: {model.readiness_gate}
          </h3>
        </div>
      </div>

      {model.summary_copy && (
        <p className="border-b border-slate-100 px-5 py-3 text-sm font-medium leading-relaxed text-slate-700">
          {model.summary_copy}
        </p>
      )}

      <div className="grid gap-4 p-5 md:grid-cols-2">
        <div>
          <div className="flex items-center gap-1.5 text-[13px] font-bold text-emerald-700">
            <CheckCircle2 size={15} /> What improved
          </div>
          <p className="mt-1.5 text-[12px] text-slate-500">
            {improved.resolved_finding_count} resolved finding(s)
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {improved.primary_finding_types_resolved.length > 0 ? (
              improved.primary_finding_types_resolved.map((t) => (
                <StatusChip key={t} label={t} color="green" mono />
              ))
            ) : (
              <p className="text-[11px] text-slate-400">
                No supported findings resolved in this run.
              </p>
            )}
          </div>
        </div>

        <div>
          <div className="flex items-center gap-1.5 text-[13px] font-bold text-amber-700">
            <ShieldAlert size={15} /> What remains blocked
          </div>
          <p className="mt-1.5 text-[12px] text-slate-500">Unresolved finding types</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {blocked.unresolved_finding_types.length > 0 ? (
              blocked.unresolved_finding_types.map((t) => (
                <StatusChip key={t} label={t} color="amber" mono />
              ))
            ) : (
              <p className="text-[11px] text-slate-400">None.</p>
            )}
          </div>
          <p className="mt-2 text-[12px] text-slate-500">Human review categories</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {blocked.human_review_categories.length > 0 ? (
              blocked.human_review_categories.map((c) => (
                <StatusChip key={c} label={c} color="amber" />
              ))
            ) : (
              <p className="text-[11px] text-slate-400">None.</p>
            )}
          </div>
        </div>
      </div>

      {model.why_not_pass && (
        <div
          className="flex items-start gap-2 border-t border-rose-100 bg-rose-50/60 px-5 py-3 text-[12.5px] font-medium text-rose-800"
          role="note"
        >
          <XCircle size={15} className="mt-0.5 shrink-0" />
          <span>{model.why_not_pass}</span>
        </div>
      )}
    </div>
  );
}
