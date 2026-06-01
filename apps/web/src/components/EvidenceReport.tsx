import { useState } from "react";
import clsx from "clsx";
import type { EvidenceModel, FindingRow } from "../types/noxus";
import { StatusChip } from "./StatusChip";

function FindingCard({ finding, openRisk }: { finding: FindingRow; openRisk: boolean }) {
  return (
    <div className="card p-4">
      <h4 className="text-[13px] font-bold text-slate-900">{finding.finding_type}</h4>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <StatusChip label={finding.severity} color={finding.severity_color} />
        <StatusChip label={finding.detection_label} color={finding.detection_color} mono />
        <StatusChip label={finding.probe_id} color="neutral" mono />
        {finding.confidence && (
          <StatusChip label={`confidence: ${finding.confidence}`} color="blue" />
        )}
        {openRisk && <StatusChip label="open risk" color="red" />}
      </div>
      <dl className="mt-2.5 space-y-0.5 text-[11.5px] text-slate-500">
        <div>
          <span className="font-semibold text-slate-700">Remediation target:</span>{" "}
          {finding.remediation_target_label}
        </div>
        <div>
          <span className="font-semibold text-slate-700">Evidence source:</span>{" "}
          {finding.evidence_source}
        </div>
      </dl>
      <pre className="code-block scroll-thin mt-2 max-h-24">{finding.evidence}</pre>
    </div>
  );
}

export function EvidenceReport({ model }: { model: EvidenceModel }) {
  const [tab, setTab] = useState<"before" | "after">("after");
  const findings = tab === "before" ? model.before_findings : model.after_findings;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-slate-500">
          Severity, detection mode, evidence, confidence, and remediation targets —
          separated for fast review. No raw JSON dump.
        </p>
        <div className="flex gap-1 rounded-lg border border-slate-200 bg-white p-1">
          {(["after", "before"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={clsx(
                "rounded-md px-3 py-1.5 text-xs font-semibold transition",
                tab === t
                  ? "bg-brand-50 text-brand-700"
                  : "text-slate-500 hover:text-slate-800",
              )}
            >
              {t === "before" ? "Before-state" : "Retest"} findings
            </button>
          ))}
        </div>
      </div>
      {findings.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {findings.map((f, i) => (
            <FindingCard key={i} finding={f} openRisk={tab === "after"} />
          ))}
        </div>
      ) : (
        <div className="card p-6 text-sm text-slate-500">
          No {tab === "before" ? "before-state" : "retest"} findings in this report.
        </div>
      )}
    </div>
  );
}
