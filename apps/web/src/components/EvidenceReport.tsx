import { useState } from "react";
import clsx from "clsx";
import type { EvidenceModel, FindingRow } from "../types/noxus";
import { SectionHeader } from "./Section";
import { StatusChip } from "./StatusChip";

function FindingCard({ finding, openRisk }: { finding: FindingRow; openRisk: boolean }) {
  return (
    <div className="nx-card p-4">
      <h3 className="text-sm font-extrabold text-white">{finding.finding_type}</h3>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <StatusChip label={finding.severity} color={finding.severity_color} />
        <StatusChip label={finding.detection_label} color={finding.detection_color} mono />
        <StatusChip label={finding.probe_id} color="neutral" mono />
        {finding.confidence && (
          <StatusChip label={`confidence: ${finding.confidence}`} color="blue" />
        )}
        {openRisk && <StatusChip label="open risk" color="red" />}
      </div>
      <dl className="mt-2.5 space-y-0.5 text-[11px] text-slate-400">
        <div>
          <span className="font-semibold text-slate-300">Remediation target:</span>{" "}
          {finding.remediation_target_label}
        </div>
        <div>
          <span className="font-semibold text-slate-300">Evidence source:</span>{" "}
          {finding.evidence_source}
        </div>
      </dl>
      <pre className="nx-scroll mt-2 max-h-28 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line-soft bg-ink-950/80 p-2.5 font-mono text-[11px] leading-relaxed text-slate-300">
        {finding.evidence}
      </pre>
    </div>
  );
}

export function EvidenceReport({ model }: { model: EvidenceModel }) {
  const [tab, setTab] = useState<"before" | "after">("after");
  const findings = tab === "before" ? model.before_findings : model.after_findings;
  return (
    <section>
      <SectionHeader
        kicker="Evidence report"
        title="Findings with remediation context"
        copy="Severity, detection mode, evidence, confidence, and remediation targets — separated for fast review. No raw dumps."
        right={
          <div className="flex gap-1 rounded-lg border border-line bg-ink-850 p-1">
            {(["before", "after"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={clsx(
                  "rounded-md px-3 py-1.5 text-xs font-bold transition",
                  tab === t
                    ? "bg-ink-700 text-white"
                    : "text-slate-400 hover:text-slate-200",
                )}
              >
                {t === "before" ? "Before-state" : "Retest"} findings
              </button>
            ))}
          </div>
        }
      />
      {findings.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {findings.map((f, i) => (
            <FindingCard key={i} finding={f} openRisk={tab === "after"} />
          ))}
        </div>
      ) : (
        <div className="nx-card p-6 text-sm text-slate-400">
          No {tab === "before" ? "before-state" : "retest"} findings in this report.
        </div>
      )}
    </section>
  );
}
