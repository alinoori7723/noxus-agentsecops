import { Clock, RefreshCw } from "lucide-react";
import type { TimeoutFailure, TuningFallback } from "../types/noxus";

// Role-specific LLM timeout banner. Replaces the old generic "LLM request timed
// out." with exactly which agent/model timed out, the retry count, and (when a
// tuning fallback recovered) an honest note that the fallback model was used.
export function TimeoutNotice({
  failure,
  fallback,
}: {
  failure: TimeoutFailure | null;
  fallback: TuningFallback | null;
}) {
  if (!failure && !(fallback && fallback.used)) return null;

  const fatal = failure?.fatal;
  const tone = fatal
    ? "border-rose-300 bg-rose-50/70 text-rose-900"
    : "border-amber-300 bg-amber-50/70 text-amber-900";

  return (
    <div className={`card flex items-start gap-3 border p-4 ${tone}`} role="alert">
      <Clock size={18} className="mt-0.5 shrink-0" />
      <div className="space-y-1.5">
        {failure && (
          <>
            <p className="text-sm font-bold">
              {failure.message ||
                `LLM request timed out during ${failure.role_label}.`}
            </p>
            <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[12px]">
              <span>
                Role: <span className="font-mono">{failure.role_label}</span>
              </span>
              {failure.model && (
                <span>
                  Model: <span className="font-mono">{failure.model}</span>
                </span>
              )}
              {failure.provider_type && (
                <span>
                  Provider: <span className="font-mono">{failure.provider_type}</span>
                </span>
              )}
              {failure.timeout_seconds != null && (
                <span>Timeout: {failure.timeout_seconds}s</span>
              )}
              <span>Retries: {failure.retry_count}</span>
            </div>
            <p className="text-[12px]">
              {fatal
                ? "The deterministic baseline below is preserved; no patches were applied and no PASS was implied."
                : "The run continued — this stage degraded but the baseline and prior stages are preserved."}
            </p>
          </>
        )}
        {fallback && fallback.used && (
          <p className="flex items-center gap-1.5 text-[12px] font-medium">
            <RefreshCw size={13} />
            Policy Tuning Agent timed out on{" "}
            <span className="font-mono">{fallback.original_model}</span>; fallback model{" "}
            <span className="font-mono">{fallback.fallback_model}</span> was used.
          </p>
        )}
      </div>
    </div>
  );
}
