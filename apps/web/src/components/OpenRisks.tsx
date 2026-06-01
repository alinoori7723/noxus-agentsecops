import { ShieldAlert, UserCheck } from "lucide-react";
import type { EvidenceModel } from "../types/noxus";
import { StatusChip } from "./StatusChip";

export function OpenRisks({ model }: { model: EvidenceModel }) {
  return (
    <div className="card border-amber-200 bg-amber-50/40 p-5">
      <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <div>
          <div className="kicker flex items-center gap-1.5 text-amber-600">
            <ShieldAlert size={13} /> Open risks
          </div>
          <div className="mt-2.5 space-y-2.5">
            {model.open_risks.length > 0 ? (
              model.open_risks.map((risk, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-amber-200 bg-white p-3.5"
                >
                  <StatusChip label="open risk" color="red" />
                  <p className="mt-2 text-sm leading-relaxed text-slate-700">{risk}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-500">No open risks reported.</p>
            )}

            {model.proprietary_context_exposure_unresolved && (
              <div className="rounded-lg border border-amber-300 bg-amber-100/60 p-4">
                <h4 className="text-sm font-bold text-amber-900">
                  Proprietary-context exposure is not auto-patched
                </h4>
                <p className="mt-1.5 text-sm leading-relaxed text-amber-800">
                  {model.proprietary_context_explanation}
                </p>
              </div>
            )}
          </div>
        </div>

        <div>
          <div className="kicker flex items-center gap-1.5 text-amber-600">
            <UserCheck size={13} /> Human review
          </div>
          <div className="mt-2.5 space-y-2.5">
            {model.human_review_requirements.length > 0 ? (
              model.human_review_requirements.map((req) => (
                <div
                  key={req}
                  className="rounded-lg border border-amber-200 bg-white p-3.5"
                >
                  <StatusChip label="human review" color="amber" />
                  <p className="mt-2 text-sm text-slate-700">{req}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-500">
                No human-review categories reported.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
