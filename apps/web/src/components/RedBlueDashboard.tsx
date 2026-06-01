import { Swords, ShieldCheck, Wrench, ArrowRight } from "lucide-react";
import type { ProbeRow, PatchRow, RedBlueModel } from "../types/noxus";
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

function PatchCard({ patch }: { patch: PatchRow }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <code className="rounded bg-sky-50 px-1.5 py-0.5 font-mono text-[11px] text-sky-700">
          {patch.operation}
        </code>
        {patch.is_safety_rail && <StatusChip label="safety rail" color="green" />}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <StatusChip label={patch.target} color="blue" />
        {patch.detail && <StatusChip label={patch.detail} color="neutral" mono />}
      </div>
      <p className="mt-2 text-[11px] text-slate-500">
        Source finding: {patch.source_finding ?? "not specified"}
      </p>
    </div>
  );
}

export function RedBlueDashboard({ model }: { model: RedBlueModel }) {
  const { red, blue } = model;
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
              <Wrench size={13} /> Patch operations
            </div>
            <p className="text-[11.5px] leading-relaxed text-slate-500">
              {blue.patch_engine_note}
            </p>
            {blue.patches.map((p, i) => (
              <PatchCard key={i} patch={p} />
            ))}

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

            <div className="kicker pt-1">Human review requirements</div>
            {blue.human_review_requirements.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {blue.human_review_requirements.map((r) => (
                  <StatusChip key={r} label={r} color="amber" />
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
