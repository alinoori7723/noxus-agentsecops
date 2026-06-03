import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import type { SchemaFailure } from "../types/noxus";

const ROLE_LABEL: Record<string, string> = {
  red: "Red Team Agent",
  judge: "Semantic Judge",
  tuning: "Policy Tuning Agent",
};

/**
 * Shown when an agent-assisted run ended in HUMAN_REVIEW_REQUIRED due to a schema
 * contract failure. It makes clear this is a PARTIAL run (deterministic baseline
 * completed) and which agent stage failed — distinct from a complete loop. The
 * sanitized excerpt is collapsed by default and never contains an API key.
 */
export function PartialRunBanner({ failure }: { failure: SchemaFailure }) {
  const [open, setOpen] = useState(false);
  const stageLabel = failure.failed_role
    ? `${ROLE_LABEL[failure.failed_role] ?? failure.failed_role} failed`
    : "An agent stage failed";

  return (
    <div className="card border-amber-300 bg-amber-50/60 p-5" role="alert">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
          <AlertTriangle size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-bold text-slate-900">
              Partial run — {stageLabel}
            </h3>
            <span className="rounded-md border border-amber-300 bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-800">
              HUMAN_REVIEW_REQUIRED
            </span>
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-700">
            The deterministic baseline completed, but the agent-assisted stage
            failed schema validation ({failure.reason}). No patches were applied.
            The deterministic baseline evidence below is preserved
            {failure.baseline_preserved
              ? ` (${failure.baseline_probe_count} probes, ${failure.baseline_finding_count} findings).`
              : "."}
          </p>

          {failure.debug_excerpt && (
            <div className="mt-3">
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-amber-800 hover:text-amber-900"
              >
                {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                Schema contract failure details
              </button>
              {open && (
                <pre className="code-block scroll-thin mt-2 max-h-48 border-amber-200 bg-white">
                  {failure.debug_excerpt}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
