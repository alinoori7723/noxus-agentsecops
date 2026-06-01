import clsx from "clsx";
import {
  Cpu,
  Bot,
  Play,
  Loader2,
  ShieldCheck,
  AlertTriangle,
  Plug,
  KeyRound,
  CheckCircle2,
} from "lucide-react";
import type { Mode, ProviderConfig } from "../types/noxus";

interface AssessmentPanelProps {
  mode: Mode;
  onModeChange: (mode: Mode) => void;
  provider: ProviderConfig;
  onGoToProvider: () => void;
  onRun: () => void;
  running: boolean;
  error: string | null;
  providerTestOk: boolean;
  providerTestStale: boolean;
}

const PROVIDER_LABELS: Record<string, string> = {
  local_openai_compatible: "Local LiteLLM / OpenAI-compatible",
  openai_compatible: "Generic OpenAI-compatible",
  gemini_native: "Gemini native",
};

function ModeCard({
  active,
  onClick,
  icon,
  title,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={clsx(
        "flex-1 rounded-xl border p-4 text-left transition",
        active
          ? "border-brand-400 bg-brand-50 ring-1 ring-brand-200"
          : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50",
      )}
    >
      <div className="flex items-center gap-2">
        <span className={active ? "text-brand-600" : "text-slate-400"}>{icon}</span>
        <span className="text-sm font-bold text-slate-900">{title}</span>
        <span
          className={clsx(
            "ml-auto h-4 w-4 rounded-full border-2",
            active ? "border-brand-600 bg-brand-600" : "border-slate-300",
          )}
        />
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-slate-500">{children}</p>
    </button>
  );
}

export function AssessmentPanel({
  mode,
  onModeChange,
  provider,
  onGoToProvider,
  onRun,
  running,
  error,
  providerTestOk,
  providerTestStale,
}: AssessmentPanelProps) {
  const isAgent = mode === "agent_assisted";
  const keyMissing = isAgent && !provider.api_key;
  const tested = providerTestOk && !providerTestStale;

  return (
    <div className="card space-y-5 p-6">
      <div className="flex flex-col gap-3 sm:flex-row">
        <ModeCard
          active={!isAgent}
          onClick={() => onModeChange("deterministic")}
          icon={<Cpu size={18} />}
          title="Deterministic Mode"
        >
          Reproducible. No AI provider or API key required. Runs the deterministic
          evaluator and patch engine end-to-end.
        </ModeCard>
        <ModeCard
          active={isAgent}
          onClick={() => onModeChange("agent_assisted")}
          icon={<Bot size={18} />}
          title="Agent-Assisted Mode"
        >
          Adds Red Team, semantic judge, and policy-tuning agents via your
          provider. Agents propose; they never apply patches.
        </ModeCard>
      </div>

      {!isAgent ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-emerald-200 bg-emerald-50 p-3.5 text-sm text-emerald-800">
          <ShieldCheck size={17} className="mt-0.5 shrink-0 text-emerald-600" />
          <span>
            <strong>No AI credentials required.</strong> Runs the deterministic
            evaluator and patch engine end-to-end and is fully reproducible.
          </span>
        </div>
      ) : (
        <div
          className={clsx(
            "rounded-lg border p-3.5 text-sm",
            keyMissing
              ? "border-amber-200 bg-amber-50 text-amber-800"
              : "border-sky-200 bg-sky-50 text-sky-800",
          )}
        >
          <div className="flex flex-wrap items-center gap-2">
            <Plug size={16} className="shrink-0" />
            <span className="font-semibold">
              Provider: {PROVIDER_LABELS[provider.provider_type]}
            </span>
            <button
              type="button"
              onClick={onGoToProvider}
              className="ml-auto inline-flex items-center gap-1 rounded-md border border-current/30 px-2.5 py-1 text-xs font-semibold hover:bg-white/50"
            >
              Provider Settings
            </button>
          </div>
          <div className="mt-2 flex items-start gap-2">
            {keyMissing ? (
              <>
                <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                <span>
                  An API key is required for Agent-Assisted Mode. Add it under
                  Provider Settings — it is used for this run only and never stored.
                </span>
              </>
            ) : (
              <span>
                Red <code className="font-mono">{provider.red_model}</code> · Judge{" "}
                <code className="font-mono">{provider.judge_model}</code> · Tuning{" "}
                <code className="font-mono">{provider.tuning_model}</code>
              </span>
            )}
          </div>
          {!keyMissing && (
            <div className="mt-2 border-t border-current/10 pt-2">
              {tested ? (
                <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-emerald-700">
                  <CheckCircle2 size={14} /> Provider connection tested successfully.
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-amber-700">
                  <AlertTriangle size={14} />
                  {providerTestStale
                    ? "Provider config changed since the last test."
                    : "Provider not tested yet."}{" "}
                  Running will make live LLM calls — test it first under Provider
                  Settings.
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2.5 rounded-lg border border-rose-200 bg-rose-50 p-3.5 text-sm text-rose-800">
          <AlertTriangle size={17} className="mt-0.5 shrink-0 text-rose-600" />
          <div>
            <div className="font-semibold">Assessment could not be completed</div>
            <div className="mt-0.5 text-rose-700">{error}</div>
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={onRun}
        disabled={running || keyMissing}
        className="btn-primary w-full py-3 text-[15px]"
      >
        {running ? (
          <>
            <Loader2 size={18} className="animate-spin" /> Running assessment...
          </>
        ) : keyMissing ? (
          <>
            <KeyRound size={18} /> Add an API key in Provider Settings to run
          </>
        ) : (
          <>
            <Play size={18} /> Run Readiness Assessment
          </>
        )}
      </button>
    </div>
  );
}
