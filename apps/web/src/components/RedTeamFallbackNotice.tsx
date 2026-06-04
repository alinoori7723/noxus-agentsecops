import { useState } from "react";
import { ShieldAlert, ChevronDown, ChevronRight } from "lucide-react";
import type { RedTeamFailure } from "../types/noxus";

/**
 * Shown when the Red Team Agent failed schema validation but the run CONTINUED
 * on the deterministic baseline (a degraded-but-honest run). This is visually
 * distinct from a complete successful Red Team run and from the
 * HUMAN_REVIEW_REQUIRED PartialRunBanner: it communicates that Noxus did not
 * abort and did not fabricate Red Team probes. The sanitized excerpt is
 * collapsed by default and never contains an API key.
 */
export function RedTeamFallbackNotice({ failure }: { failure: RedTeamFailure }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="card border-amber-300 bg-amber-50/60 p-5" role="status">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
          <ShieldAlert size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-bold text-slate-900">
              Red Team Agent failed — continued on deterministic baseline
            </h3>
            <span className="rounded-md border border-amber-300 bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-800">
              FALLBACK USED
            </span>
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-700">
            Red Team Agent failed schema validation. Noxus continued using
            deterministic baseline evidence
            {failure.baseline_preserved
              ? ` (${failure.baseline_probe_count} probes, ${failure.baseline_finding_count} findings).`
              : "."}{" "}
            No Red Team probes were fabricated; the policy tuning agent ran from
            the deterministic baseline findings.
          </p>

          {failure.debug_excerpt && (
            <div className="mt-3">
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-amber-800 hover:text-amber-900"
              >
                {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                Red Team schema failure details
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
