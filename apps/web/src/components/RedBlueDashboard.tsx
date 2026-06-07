import { Swords, ShieldCheck, Wrench, ArrowRight, AlertTriangle } from "lucide-react";
import type { ChipColor, PatchRow, ProbeRow, RedBlueModel } from "../types/noxus";
import { StatusChip } from "./StatusChip";

const SAFETY_RAIL_HEADING = "[CRITICAL_SAFETY_RAILS]";

function ProbeCard({ probe }: { probe: ProbeRow }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600">
          {probe.probe_id}
        </code>
        <span className="text-[13px] font-bold text-slate-900">
          {probe.probe_type}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <StatusChip label={probe.status} color={probe.status_color} />
        <StatusChip label={probe.detection_label} color={probe.detection_color} mono />
        <StatusChip label={`${probe.num_findings} findings`} color="neutral" />
      </div>
      {probe.evidence.length > 0 ? (
        <div className="mt-2 space-y-1.5">
          {probe.evidence.map((ev, i) => (
            <pre key={i} className="code-block scroll-thin max-h-24">
              {ev}
            </pre>
          ))}
        </div>
      ) : (
        <p className="mt-1.5 text-[11px] text-slate-400">
          No findings emitted for this probe.
        </p>
      )}
    </div>
  );
}

const PATCH_STATUS_META: Record<string, { label: string; color: ChipColor }> = {
  applied_and_resolved: { label: "applied · primary resolved", color: "green" },
  applied_but_related_risk_unresolved: {
    label: "applied · primary resolved · related risk unresolved",
    color: "amber",
  },
  applied_but_primary_unresolved: { label: "applied · primary unresolved", color: "amber" },
  applied_requires_human_review: { label: "applied · human review", color: "amber" },
  rejected_unlinked: { label: "rejected · unlinked", color: "red" },
};

function PatchCard({ patch }: { patch: PatchRow }) {
  const status = PATCH_STATUS_META[patch.status] ?? {
    label: patch.status,
    color: "neutral" as ChipColor,
  };
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <code className="rounded bg-sky-50 px-1.5 py-0.5 font-mono text-[11px] text-sky-700">
          {patch.operation}
        </code>
        {patch.is_safety_rail && <StatusChip label="safety rail" color="green" />}
        <StatusChip label={status.label} color={status.color} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <StatusChip label={patch.target} color="blue" />
        {patch.detail && <StatusChip label={patch.detail} color="neutral" mono />}
      </div>
      <p className="mt-2 text-[11px] text-slate-500">
        Primary source:{" "}
        <span className="font-mono font-bold text-slate-800">
          {patch.primary_source_label}
        </span>
      </p>
      {patch.related_finding_groups.same_category_related.length > 0 && (
        <p className="mt-0.5 text-[11px] text-slate-400">
          Related findings from same category:{" "}
          <span className="font-mono text-slate-500">
            {patch.related_finding_groups.same_category_related.join(", ")}
          </span>
        </p>
      )}
      {patch.related_finding_groups.leakage_from_same_probe.length > 0 && (
        <p className="mt-0.5 text-[11px] text-slate-400">
          Leakage from same probe:{" "}
          <span className="font-mono text-slate-500">
            {patch.related_finding_groups.leakage_from_same_probe.join(", ")}
          </span>
        </p>
      )}
      {patch.related_finding_groups.generic_policy_related.length > 0 && (
        <p className="mt-0.5 text-[11px] text-slate-400">
          Generic policy-related finding:{" "}
          <span className="font-mono text-slate-500">
            {patch.related_finding_groups.generic_policy_related.join(", ")}
          </span>
        </p>
      )}
    </div>
  );
}

export function RedBlueDashboard({ model }: { model: RedBlueModel }) {
  const { red, blue } = model;
  const rem = blue.remediation;
  const preview = blue.safety_rail_preview;
  const hasRealRail = preview.includes(SAFETY_RAIL_HEADING);
  const failing = red.baseline_probes.filter((p) => !p.passed);

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-slate-50/70 px-5 py-3.5">
        <div>
          <div className="kicker">Red Team / Blue Team</div>
          <h3 className="mt-0.5 text-base font-bold text-slate-900">
            Security audit cockpit
          </h3>
        </div>
        <div className="ml-auto hidden items-center gap-2 text-xs font-medium text-slate-500 md:flex">
          LLM proposes
          <ArrowRight size={14} className="text-slate-300" />
          deterministic engine applies
          <ArrowRight size={14} className="text-slate-300" />
          open risks stay visible
        </div>
      </div>

      <div className="grid lg:grid-cols-2">
        {/* RED */}
        <div className="border-b border-slate-200 lg:border-b-0 lg:border-r">
          <div className="border-b border-rose-100 bg-rose-50/60 px-5 py-3.5">
            <div className="flex items-center gap-2">
              <Swords size={17} className="text-rose-500" />
              <h4 className="text-sm font-bold text-slate-900">Red Team</h4>
            </div>
            <p className="mt-0.5 text-[12px] text-slate-500">
              Structured adversarial probes and evidence
            </p>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              <StatusChip
                label={`baseline failures: ${red.before_summary.failed_probes}`}
                color="red"
              />
              <StatusChip
                label={`retest failures: ${red.after_summary.failed_probes}`}
                color="amber"
              />
              <StatusChip
                label={`retest findings: ${red.after_summary.findings}`}
                color="neutral"
              />
            </div>
          </div>
          <div className="space-y-3 p-4">
            <div className="kicker">Before-state failures</div>
            {failing.map((p) => (
              <ProbeCard key={`b-${p.probe_id}`} probe={p} />
            ))}
            <div className="kicker pt-1">Retest probes</div>
            {red.retest_probes.map((p) => (
              <ProbeCard key={`r-${p.probe_id}`} probe={p} />
            ))}
          </div>
        </div>

        {/* BLUE */}
        <div>
          <div className="border-b border-sky-100 bg-sky-50/60 px-5 py-3.5">
            <div className="flex items-center gap-2">
              <ShieldCheck size={17} className="text-sky-600" />
              <h4 className="text-sm font-bold text-slate-900">Blue Team</h4>
            </div>
            <p className="mt-0.5 text-[12px] text-slate-500">
              Schema-bound patches and deterministic enforcement
            </p>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              <StatusChip
                label={`patch operations: ${blue.patches.length}`}
                color="blue"
              />
              <StatusChip label="deterministic engine" color="green" />
              <StatusChip
                label={`human review: ${blue.human_review_requirements.length}`}
                color="amber"
              />
            </div>
          </div>
          <div className="space-y-3 p-4">
            <div className="kicker flex items-center gap-1.5">
              <Wrench size={13} /> Readiness gate vs remediation progress
            </div>
            <div className="flex flex-wrap gap-1.5">
              <StatusChip
                label={`readiness gate: ${rem.readiness_gate}`}
                color={rem.readiness_gate === "PASS" ? "green" : "amber"}
              />
              <StatusChip
                label={`readiness gate score: ${rem.readiness_gate_score}/100`}
                color={rem.readiness_gate_score > 0 ? "green" : "amber"}
              />
              <StatusChip
                label={`remediation progress: ${rem.remediation_progress.label}`}
                color={rem.remediation_progress.resolved > 0 ? "green" : "neutral"}
              />
            </div>
            {rem.after_score_explanation && (
              <p className="text-[12px] font-medium text-amber-700">
                {rem.after_score_explanation}
              </p>
            )}
            {rem.gate_blocked_explanation && (
              <div
                className="rounded-lg border border-amber-300 bg-amber-50/70 p-3 text-[12px] font-medium text-amber-800"
                role="note"
              >
                <p>{rem.gate_blocked_explanation}</p>
                <p className="mt-0.5 text-amber-700">Gate remains blocked.</p>
                {rem.gate_blocking_reason && (
                  <p className="mt-0.5 font-mono text-[11px] text-amber-700">
                    {rem.gate_blocking_reason}
                  </p>
                )}
              </div>
            )}

            <div className="kicker flex items-center gap-1.5 pt-1">
              <Wrench size={13} /> Probe / finding mapping matrix
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-[12px] text-slate-600">
              <p className="leading-relaxed">{rem.probe_finding_mapping.note}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <StatusChip
                  label={`Baseline: ${rem.probe_finding_mapping.baseline_label}`}
                  color="red"
                />
                <StatusChip
                  label={`Retest: ${rem.probe_finding_mapping.retest_label}`}
                  color="amber"
                />
                <StatusChip
                  label={rem.probe_finding_mapping.resolved_label}
                  color="green"
                />
                <StatusChip
                  label={`Unresolved types: ${
                    rem.probe_finding_mapping.unresolved_finding_types.join(", ") || "none"
                  }`}
                  color="neutral"
                />
              </div>
              <p className="mt-2 text-[11px] text-slate-500">
                Human review accounts for{" "}
                {rem.human_review_derived_finding_instance_count} unresolved finding
                instance(s) across {rem.human_review_derived_finding_type_count} finding
                type(s).
                {rem.unresolved_not_human_reviewed.length > 0 && (
                  <>
                    {" "}
                    {rem.unresolved_not_human_reviewed.length} unresolved instance(s)
                    are listed as not human-reviewed with a reason.
                  </>
                )}
              </p>
            </div>

            <div className="kicker flex items-center gap-1.5 pt-1">
              <Wrench size={13} /> Remediation effectiveness
            </div>
            <div className="flex flex-wrap gap-1.5">
              <StatusChip
                label={`patch operations applied: ${rem.patch_application_count}`}
                color="blue"
              />
              <StatusChip
                label={`resolved findings: ${rem.resolved_finding_count}`}
                color="green"
              />
              <StatusChip
                label={`unresolved findings: ${rem.unresolved_finding_count}`}
                color={rem.unresolved_finding_count > 0 ? "amber" : "green"}
              />
              {rem.rejected_proposal_count > 0 && (
                <StatusChip
                  label={`rejected proposals: ${rem.rejected_proposal_count}`}
                  color="red"
                />
              )}
            </div>
            {blue.blocking_explanation && (
              <div
                className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50/70 p-3 text-[12px] font-medium text-amber-800"
                role="alert"
              >
                <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                <span>{blue.blocking_explanation}</span>
              </div>
            )}

            <div className="kicker flex items-center gap-1.5 pt-1">
              <Wrench size={13} /> Patch operations
            </div>
            <p className="text-[11.5px] leading-relaxed text-slate-500">
              {blue.patch_engine_note}
            </p>
            {blue.patches.map((p, i) => (
              <PatchCard key={i} patch={p} />
            ))}

            {blue.rejected_proposals.length > 0 && (
              <>
                <div className="kicker pt-1">
                  Rejected / unlinked proposals (not applied)
                </div>
                {blue.rejected_proposals.map((p, i) => (
                  <PatchCard key={`rej-${i}`} patch={p} />
                ))}
              </>
            )}

            <div className="kicker pt-1">Safety rail preview</div>
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              {hasRealRail ? (
                <>
                  <StatusChip
                    label={`${SAFETY_RAIL_HEADING} · real telemetry`}
                    color="green"
                    mono
                  />
                  <pre className="code-block scroll-thin mt-2 max-h-44 border-emerald-200 bg-emerald-50/40 text-emerald-900">
                    {preview}
                  </pre>
                </>
              ) : (
                <p className="text-xs text-slate-500">{preview}</p>
              )}
            </div>

            <div className="kicker pt-1">
              Human review requirements (derived from unresolved findings)
            </div>
            {blue.human_review_derivation.length > 0 ? (
              <div className="space-y-2">
                {blue.human_review_derivation.map((row) => (
                  <div
                    key={row.category}
                    className="rounded-lg border border-amber-200 bg-amber-50/50 p-3"
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <StatusChip label={row.category} color="amber" />
                      <StatusChip
                        label={
                          row.source === "derived_from_retest"
                            ? "derived from retest"
                            : "proposed by agent"
                        }
                        color={row.source === "derived_from_retest" ? "blue" : "neutral"}
                      />
                    </div>
                    <p className="mt-1.5 text-[11.5px] text-slate-600">{row.reason}</p>
                    {row.derived_from_finding_types.length > 0 && (
                      <p className="mt-1 text-[11px] text-slate-500">
                        finding types:{" "}
                        <span className="font-mono text-slate-700">
                          {row.derived_from_finding_types.join(", ")}
                        </span>
                      </p>
                    )}
                    {row.derived_from_probe_ids.length > 0 && (
                      <p className="mt-0.5 text-[11px] text-slate-500">
                        probes:{" "}
                        <span className="font-mono text-slate-700">
                          {row.derived_from_probe_ids.join(", ")}
                        </span>
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-slate-400">
                No human-review categories reported.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
