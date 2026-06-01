import { ShieldAlert, UserCheck } from "lucide-react";
import type { EvidenceModel } from "../types/noxus";
import { SectionHeader } from "./Section";
import { StatusChip } from "./StatusChip";

export function OpenRisks({ model }: { model: EvidenceModel }) {
  return (
    <section>
      <SectionHeader
        kicker="Open risks / human review"
        title="Unresolved risk remains visible"
        copy="Noxus keeps unsupported proprietary-context exposure in front of the reviewer instead of cosmetically promoting the output."
      />
      <div className="nx-panel border-amber-500/30 bg-amber-500/[0.04] p-5">
        <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
          <div>
            <div className="nx-kicker flex items-center gap-1.5 text-amber-300/80">
              <ShieldAlert size={13} /> Open risks
            </div>
            <div className="mt-2.5 space-y-2.5">
              {model.open_risks.length > 0 ? (
                model.open_risks.map((risk, i) => (
                  <div
                    key={i}
                    className="rounded-xl border border-amber-500/30 bg-ink-900/60 p-3.5"
                  >
                    <StatusChip label="open risk" color="red" />
                    <p className="mt-2 text-sm leading-relaxed text-slate-300">
                      {risk}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-400">No open risks reported.</p>
              )}

              {model.proprietary_context_exposure_unresolved && (
                <div className="rounded-xl border border-amber-500/50 bg-amber-500/10 p-4">
                  <h3 className="text-sm font-extrabold text-amber-100">
                    Proprietary-context exposure is not auto-patched
                  </h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-amber-100/80">
                    {model.proprietary_context_explanation}
                  </p>
                </div>
              )}
            </div>
          </div>

          <div>
            <div className="nx-kicker flex items-center gap-1.5 text-amber-300/80">
              <UserCheck size={13} /> Human review
            </div>
            <div className="mt-2.5 space-y-2.5">
              {model.human_review_requirements.length > 0 ? (
                model.human_review_requirements.map((req) => (
                  <div
                    key={req}
                    className="rounded-xl border border-amber-500/30 bg-ink-900/60 p-3.5"
                  >
                    <StatusChip label="human review" color="amber" />
                    <p className="mt-2 text-sm text-slate-300">{req}</p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-400">
                  No human-review categories reported.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
