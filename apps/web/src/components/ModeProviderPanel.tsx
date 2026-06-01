import { useState } from "react";
import clsx from "clsx";
import {
  Cpu,
  Bot,
  KeyRound,
  Eye,
  EyeOff,
  Play,
  Loader2,
  ShieldCheck,
  Lock,
  AlertTriangle,
} from "lucide-react";
import type { Mode, ProviderConfig, ProviderType } from "../types/noxus";
import { SectionHeader } from "./Section";

const GEMINI_PRESETS = [
  "gemini-3.5-flash",
  "gemini-3.1-pro-preview",
  "gemini-3.1-flash-lite-preview",
];

const PROVIDER_OPTIONS: { value: ProviderType; label: string; hint: string }[] = [
  {
    value: "local_openai_compatible",
    label: "Local LLM / LiteLLM",
    hint: "OpenAI-style gateway on your machine (default http://localhost:4000/v1).",
  },
  {
    value: "openai_compatible",
    label: "OpenAI-compatible API",
    hint: "Any vendor exposing /v1/chat/completions. Set the base URL.",
  },
  {
    value: "gemini_native",
    label: "Gemini native",
    hint: "Google Generative Language API. Model IDs change — presets are defaults, not claims.",
  },
];

interface ModeProviderPanelProps {
  mode: Mode;
  onModeChange: (mode: Mode) => void;
  provider: ProviderConfig;
  onProviderChange: (next: ProviderConfig) => void;
  onRun: () => void;
  running: boolean;
  error: string | null;
}

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
      className={clsx(
        "flex-1 rounded-xl border p-4 text-left transition",
        active
          ? "border-accent/60 bg-accent/10 shadow-glow"
          : "border-line bg-ink-850/70 hover:border-line/80 hover:bg-ink-800/70",
      )}
    >
      <div className="flex items-center gap-2">
        <span className={active ? "text-accent-soft" : "text-slate-400"}>{icon}</span>
        <span className="text-sm font-extrabold text-white">{title}</span>
        <span
          className={clsx(
            "ml-auto h-3.5 w-3.5 rounded-full border-2",
            active ? "border-accent bg-accent" : "border-slate-600",
          )}
        />
      </div>
      <p className="mt-2 text-xs leading-relaxed text-slate-400">{children}</p>
    </button>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-wide text-slate-400">
        {label}
      </span>
      {children}
    </label>
  );
}

export function ModeProviderPanel({
  mode,
  onModeChange,
  provider,
  onProviderChange,
  onRun,
  running,
  error,
}: ModeProviderPanelProps) {
  const [showKey, setShowKey] = useState(false);
  const isAgent = mode === "agent_assisted";
  const pt = provider.provider_type;
  const showBaseUrl = pt !== "gemini_native";

  const set = (patch: Partial<ProviderConfig>) =>
    onProviderChange({ ...provider, ...patch });

  const keyMissing = isAgent && !provider.api_key;

  return (
    <section>
      <SectionHeader
        kicker="Assessment controls"
        title="Mode &amp; provider"
        copy="Deterministic Mode is the default judge path and needs no credentials. Agent-Assisted Mode adds schema-bound LLM agents that only propose changes — the deterministic engine still applies them."
      />

      <div className="nx-panel space-y-5 p-5">
        <div className="flex flex-col gap-3 sm:flex-row">
          <ModeCard
            active={!isAgent}
            onClick={() => onModeChange("deterministic")}
            icon={<Cpu size={17} />}
            title="Deterministic Mode"
          >
            Reproducible. No AI provider or API key required. Runs the
            deterministic evaluator and patch engine end-to-end.
          </ModeCard>
          <ModeCard
            active={isAgent}
            onClick={() => onModeChange("agent_assisted")}
            icon={<Bot size={17} />}
            title="Agent-Assisted Mode"
          >
            Adds Red Team, semantic judge, and policy-tuning agents via your
            provider. Agents propose; they never apply patches.
          </ModeCard>
        </div>

        {isAgent && (
          <div className="space-y-4 rounded-xl border border-line bg-ink-950/40 p-4">
            <Field label="Provider type">
              <select
                className="nx-field"
                value={pt}
                onChange={(e) =>
                  set({ provider_type: e.target.value as ProviderType })
                }
              >
                {PROVIDER_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value} className="bg-ink-900">
                    {o.label}
                  </option>
                ))}
              </select>
              <span className="mt-1.5 block text-[11px] leading-relaxed text-slate-500">
                {PROVIDER_OPTIONS.find((o) => o.value === pt)?.hint}
              </span>
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              {showBaseUrl && (
                <Field label="Base URL">
                  <input
                    type="text"
                    className="nx-field font-mono text-xs"
                    placeholder={
                      pt === "local_openai_compatible"
                        ? "http://localhost:4000/v1"
                        : "https://your-endpoint/v1"
                    }
                    value={provider.base_url ?? ""}
                    onChange={(e) => set({ base_url: e.target.value })}
                  />
                </Field>
              )}
              <Field label="API key">
                <div className="relative">
                  <input
                    type={showKey ? "text" : "password"}
                    autoComplete="off"
                    className={clsx(
                      "nx-field pr-10 font-mono text-xs",
                      keyMissing && "border-amber-500/50",
                    )}
                    placeholder="sk-…"
                    value={provider.api_key ?? ""}
                    onChange={(e) => set({ api_key: e.target.value })}
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((v) => !v)}
                    className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-slate-500 hover:text-slate-300"
                    aria-label={showKey ? "Hide API key" : "Show API key"}
                  >
                    {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </Field>
            </div>

            {pt === "gemini_native" && (
              <Field label="Gemini model preset">
                <select
                  className="nx-field"
                  value={
                    GEMINI_PRESETS.includes(provider.red_model ?? "")
                      ? provider.red_model
                      : "__custom__"
                  }
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v === "__custom__") return;
                    set({ red_model: v, judge_model: v, tuning_model: v });
                  }}
                >
                  {GEMINI_PRESETS.map((m) => (
                    <option key={m} value={m} className="bg-ink-900">
                      {m}
                    </option>
                  ))}
                  <option value="__custom__" className="bg-ink-900">
                    Custom (type model IDs below)
                  </option>
                </select>
                <span className="mt-1.5 block text-[11px] leading-relaxed text-slate-500">
                  Presets are convenience defaults, not availability guarantees.
                  You can type any custom Gemini model ID in the fields below.
                </span>
              </Field>
            )}

            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Red model">
                <input
                  type="text"
                  className="nx-field font-mono text-xs"
                  placeholder="red model id"
                  value={provider.red_model ?? ""}
                  onChange={(e) => set({ red_model: e.target.value })}
                />
              </Field>
              <Field label="Judge model">
                <input
                  type="text"
                  className="nx-field font-mono text-xs"
                  placeholder="judge model id"
                  value={provider.judge_model ?? ""}
                  onChange={(e) => set({ judge_model: e.target.value })}
                />
              </Field>
              <Field label="Tuning model">
                <input
                  type="text"
                  className="nx-field font-mono text-xs"
                  placeholder="tuning model id"
                  value={provider.tuning_model ?? ""}
                  onChange={(e) => set({ tuning_model: e.target.value })}
                />
              </Field>
            </div>

            <p className="flex items-start gap-2 rounded-lg border border-line bg-ink-900/60 p-3 text-[11px] leading-relaxed text-slate-400">
              <Lock size={14} className="mt-0.5 shrink-0 text-emerald-400" />
              <span>
                Used for this run only. The API key is sent once to the local
                backend, kept in memory for the request, and is{" "}
                <strong className="text-slate-200">
                  never stored in reports, audit export, logs, or browser storage
                </strong>
                .
              </span>
            </p>
          </div>
        )}

        {!isAgent && (
          <div className="flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/8 p-3 text-sm text-emerald-200">
            <ShieldCheck size={16} />
            Ready to assess — deterministic path, no credentials required.
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <button
          type="button"
          onClick={onRun}
          disabled={running || keyMissing}
          className={clsx(
            "flex w-full items-center justify-center gap-2 rounded-xl px-5 py-3.5 text-sm font-extrabold transition",
            running || keyMissing
              ? "cursor-not-allowed bg-ink-700 text-slate-400"
              : "bg-accent text-white shadow-glow hover:bg-indigo-500",
          )}
        >
          {running ? (
            <>
              <Loader2 size={17} className="animate-spin" /> Running assessment…
            </>
          ) : keyMissing ? (
            <>
              <KeyRound size={17} /> Enter an API key to run Agent-Assisted Mode
            </>
          ) : (
            <>
              <Play size={17} /> Run Readiness Assessment
            </>
          )}
        </button>
      </div>
    </section>
  );
}
