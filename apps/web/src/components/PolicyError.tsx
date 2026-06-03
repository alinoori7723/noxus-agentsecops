import { FileWarning, RotateCcw } from "lucide-react";
import type { PolicyErrorDetail } from "../types/noxus";
import { StatusChip } from "./StatusChip";

interface PolicyErrorProps {
  detail: PolicyErrorDetail;
  onResetPolicy: () => void;
}

/**
 * A clean, user-facing Security Policy validation error. It renders the friendly
 * message, the unsupported keys, and a minimal supported example — never a raw
 * Pydantic dump or validation URL.
 */
export function PolicyError({ detail, onResetPolicy }: PolicyErrorProps) {
  const unsupported = detail.unsupported_keys ?? [];
  const allowed = detail.allowed_keys ?? [];
  return (
    <div className="card border-rose-200 bg-rose-50/50 p-5" role="alert">
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-rose-100 text-rose-600">
          <FileWarning size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-bold text-slate-900">
            {detail.message}
          </h3>
          <p className="mt-1 text-[13px] leading-relaxed text-slate-600">
            Fix the Security Policy YAML to match the supported schema, then run the
            assessment again.
          </p>

          {unsupported.length > 0 && (
            <div className="mt-3">
              <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
                Unsupported keys
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {unsupported.map((k) => (
                  <StatusChip key={k} label={k} color="red" mono />
                ))}
              </div>
            </div>
          )}

          {allowed.length > 0 && (
            <div className="mt-3">
              <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
                Supported top-level keys
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {allowed.map((k) => (
                  <StatusChip key={k} label={k} color="neutral" mono />
                ))}
              </div>
            </div>
          )}

          {detail.example_yaml && (
            <div className="mt-3">
              <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
                Expected minimal schema
              </div>
              <pre className="code-block scroll-thin mt-1.5 max-h-56">
                {detail.example_yaml}
              </pre>
            </div>
          )}

          <button
            type="button"
            onClick={onResetPolicy}
            className="btn-ghost mt-4 text-rose-700 hover:border-rose-300"
          >
            <RotateCcw size={14} /> Reset policy to sample
          </button>
        </div>
      </div>
    </div>
  );
}
