import { Swords, ShieldCheck, Wrench } from "lucide-react";
import type { ProbeRow, PatchRow, RedBlueModel } from "../types/noxus";
import { SectionHeader } from "./Section";
import { StatusChip } from "./StatusChip";

const SAFETY_RAIL_HEADING = "[CRITICAL_SAFETY_RAILS]";

function ProbeCard({ probe }: { probe: ProbeRow }) {
  return (
    <div className="nx-card p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <code className="rounded bg-ink-950/70 px-1.5 py-0.5 font-mono text-[11px] text-slate-300">
          {probe.probe_id}
        </code>
        <span className="text-sm font-bold text-white">{probe.probe_type}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <StatusChip label={probe.status} color={probe.status_color} />
        <StatusChip label={probe.detection_label} color={probe.detection_color} mono />
        <StatusChip label={`${probe.num_findings} findings`} color="neutral" />
      </div>
      {probe.evidence.length > 0 ? (
        <div className="mt-2.5 space-y-1.5">
          {probe.evidence.map((ev, i) => (
            <pre
              key={i}
              className="nx-scroll max-h-28 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line-soft bg-ink-950/80 p-2.5 font-mono text-[11px] leading-relaxed text-slate-300"
            >
              {ev}
            </pre>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-[11px] text-slate-500">
          No findings emitted for this probe.
        </p>
      )}
    </div>
  );
}

function PatchCard({ patch }: { patch: PatchRow }) {
  return (
    <div className="nx-card p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <code className="rounded bg-ink-950/70 px-1.5 py-0.5 font-mono text-[11px] text-sky-300">
          {patch.operation}
        </code>
        {patch.is_safety_rail && (
          <StatusChip label="safety rail" color="green" />
        )}
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

function TeamHeader({
  icon,
  title,
  copy,
  tone,
  chips,
}: {
  icon: React.ReactNode;
  title: string;
  copy: string;
  tone: "red" | "blue";
  chips: React.ReactNode;
}) {
  const grad =
    tone === "red"
      ? "from-rose-500/15 to-transparent border-rose-500/30"
      : "from-sky-500/15 to-transparent border-sky-500/30";
  const ic = tone === "red" ? "text-rose-300" : "text-sky-300";
  return (
    <div className={`border-b bg-gradient-to-r ${grad} p-4`}>
      <div className="flex items-center gap-2">
        <span className={ic}>{icon}</span>
        <h3 className="text-base font-black text-white">{title}</h3>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-slate-400">{copy}</p>
      <div className="mt-2.5 flex flex-wrap gap-1.5">{chips}</div>
    </div>
  );
}

export function RedBlueDashboard({ model }: { model: RedBlueModel }) {
  const { red, blue } = model;
  const preview = blue.safety_rail_preview;
  const hasRealRail = preview.includes(SAFETY_RAIL_HEADING);

  return (
    <section>
      <SectionHeader
        kicker="Red Team / Blue Team"
        title="Security audit cockpit"
        copy="The core loop: Red Team evidence drives structured patch operations, and the deterministic engine applies only the allowed changes. Unresolved risk stays visible."
      />
      <div className="grid gap-4 xl:grid-cols-2">
        {/* RED TEAM */}
        <div className="nx-panel overflow-hidden">
          <TeamHeader
            tone="red"
            icon={<Swords size={18} />}
            title={red.title}
            copy="Probe outcomes, detection modes, pass/fail state, and evidence snippets."
            chips={
              <>
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
              </>
            }
          />
          <div className="space-y-3 p-4">
            <div className="nx-kicker">Before-state failures</div>
            {red.baseline_probes
              .filter((p) => !p.passed)
              .map((p) => (
                <ProbeCard key={`b-${p.probe_id}`} probe={p} />
              ))}
            <div className="nx-kicker pt-1">Retest probes</div>
            {red.retest_probes.map((p) => (
              <ProbeCard key={`r-${p.probe_id}`} probe={p} />
            ))}
          </div>
        </div>

        {/* BLUE TEAM */}
        <div className="nx-panel overflow-hidden">
          <TeamHeader
            tone="blue"
            icon={<ShieldCheck size={18} />}
            title={blue.title}
            copy={blue.patch_engine_note}
            chips={
              <>
                <StatusChip
                  label={`patch operations: ${blue.patches.length}`}
                  color="blue"
                />
                <StatusChip label="deterministic engine" color="green" />
                <StatusChip
                  label={`human review: ${blue.human_review_requirements.length}`}
                  color="amber"
                />
              </>
            }
          />
          <div className="space-y-3 p-4">
            <div className="nx-kicker flex items-center gap-1.5">
              <Wrench size={13} /> Patch operations
            </div>
            {blue.patches.map((p, i) => (
              <PatchCard key={i} patch={p} />
            ))}

            <div className="nx-kicker pt-1">Safety rail preview</div>
            <div className="nx-card p-3.5">
              {hasRealRail ? (
                <>
                  <StatusChip
                    label={`${SAFETY_RAIL_HEADING} · real telemetry`}
                    color="green"
                    mono
                  />
                  <pre className="nx-scroll mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line-soft bg-ink-950/80 p-3 font-mono text-[11px] leading-relaxed text-emerald-100">
                    {preview}
                  </pre>
                </>
              ) : (
                <p className="text-xs text-slate-400">{preview}</p>
              )}
            </div>

            <div className="nx-kicker pt-1">Human review requirements</div>
            {blue.human_review_requirements.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {blue.human_review_requirements.map((r) => (
                  <StatusChip key={r} label={r} color="amber" />
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-slate-500">
                No human-review categories reported.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
