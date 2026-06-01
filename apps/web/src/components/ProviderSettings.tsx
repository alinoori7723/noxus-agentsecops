import { useState } from "react";
import clsx from "clsx";
import {
  Eye,
  EyeOff,
  Lock,
  Server,
  Globe,
  Sparkles,
  Activity,
  Loader2,
  CheckCircle2,
  XCircle,
  Swords,
  Gavel,
  Wrench,
} from "lucide-react";
import type {
  AgentRole,
  ProviderConfig,
  ProviderType,
  ProviderTestResponse,
} from "../types/noxus";
import { StatusChip } from "./StatusChip";

const GEMINI_PRESETS = [
  "gemini-3.5-flash",
  "gemini-3.1-pro-preview",
  "gemini-3.1-flash-lite-preview",
];

const PROVIDER_OPTIONS: {
  value: ProviderType;
  label: string;
  hint: string;
  icon: typeof Server;
}[] = [
  {
    value: "local_openai_compatible",
    label: "Local LiteLLM / OpenAI-compatible",
    hint: "OpenAI-style gateway on your machine (default http://localhost:4000/v1).",
    icon: Server,
  },
  {
    value: "openai_compatible",
    label: "Generic OpenAI-compatible",
    hint: "Any vendor exposing /v1/chat/completions. Set the base URL.",
    icon: Globe,
  },
  {
    value: "gemini_native",
    label: "Gemini native",
    hint: "Google Generative Language API. Model IDs change — presets are defaults, not claims.",
    icon: Sparkles,
  },
];

const ROLE_FIELDS: {
  key: "red_model" | "judge_model" | "tuning_model";
  label: string;
  purpose: string;
  icon: typeof Swords;
}[] = [
  { key: "red_model", label: "Red model", purpose: "Generates adversarial probes", icon: Swords },
  { key: "judge_model", label: "Judge model", purpose: "Reviews semantic violations", icon: Gavel },
  { key: "tuning_model", label: "Tuning model", purpose: "Proposes schema-bound patches", icon: Wrench },
];

export interface ProviderTestState {
  status: "idle" | "testing" | "done";
  response: ProviderTestResponse | null;
  error: string | null;
  stale: boolean;
}

interface ProviderSettingsProps {
  provider: ProviderConfig;
  onChange: (next: ProviderConfig) => void;
  testState: ProviderTestState;
  onTest: (roles: AgentRole[]) => void;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-wide text-slate-500">
        {label}
      </span>
      {children}
    </label>
  );
}

function Diagnostics({ testState }: { testState: ProviderTestState }) {
  const { status, response, error, stale } = testState;
  if (status === "idle") return null;
  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Activity size={16} className="text-brand-600" />
        <h3 className="text-sm font-bold text-slate-900">Provider diagnostics</h3>
        {status === "testing" && (
          <StatusChip label="testing…" color="blue" />
        )}
        {status === "done" && response && (
          <StatusChip
            label={response.ok ? "all models ok" : "issues found"}
            color={response.ok ? "green" : "red"}
          />
        )}
        {stale && status === "done" && (
          <StatusChip label="config changed since test" color="amber" />
        )}
        {response && (
          <span className="ml-auto text-[11px] text-slate-400">
            checked {new Date(response.checked_at_utc).toLocaleTimeString()} ·{" "}
            {response.provider_type}
          </span>
        )}
      </div>

      {error && (
        <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {error}
        </p>
      )}

      {response && (
        <div className="mt-3 grid gap-2.5 sm:grid-cols-3">
          {response.results.map((r) => (
            <div
              key={r.role}
              className={clsx(
                "rounded-lg border p-3",
                r.ok ? "border-emerald-200 bg-emerald-50/50" : "border-rose-200 bg-rose-50/50",
              )}
            >
              <div className="flex items-center gap-1.5">
                {r.ok ? (
                  <CheckCircle2 size={15} className="text-emerald-600" />
                ) : (
                  <XCircle size={15} className="text-rose-600" />
                )}
                <span className="text-[12px] font-bold capitalize text-slate-900">
                  {r.role}
                </span>
                <span className="ml-auto text-[11px] text-slate-400">
                  {r.latency_ms}ms
                </span>
              </div>
              <div className="mt-1 truncate font-mono text-[11px] text-slate-600">
                {r.model}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1">
                <StatusChip
                  label={r.response_validated ? "valid JSON" : "no valid JSON"}
                  color={r.response_validated ? "green" : "amber"}
                />
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
                {r.message}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ProviderSettings({
  provider,
  onChange,
  testState,
  onTest,
}: ProviderSettingsProps) {
  const [showKey, setShowKey] = useState(false);
  const pt = provider.provider_type;
  const showBaseUrl = pt !== "gemini_native";
  const set = (patch: Partial<ProviderConfig>) => onChange({ ...provider, ...patch });
  const canTest = Boolean(provider.api_key) && testState.status !== "testing";

  return (
    <div className="space-y-4">
      <div className="card p-5">
        <span className="kicker">Provider type</span>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          {PROVIDER_OPTIONS.map((o) => {
            const Icon = o.icon;
            const active = pt === o.value;
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => set({ provider_type: o.value })}
                aria-pressed={active}
                className={clsx(
                  "rounded-xl border p-3.5 text-left transition",
                  active
                    ? "border-brand-400 bg-brand-50 ring-1 ring-brand-200"
                    : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50",
                )}
              >
                <Icon size={18} className={active ? "text-brand-600" : "text-slate-400"} />
                <div className="mt-2 text-[13px] font-bold text-slate-900">{o.label}</div>
                <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500">
                  {o.hint}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      <div className="card space-y-4 p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          {showBaseUrl && (
            <Field label="Base URL">
              <input
                type="text"
                className="field font-mono text-xs"
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
                className="field pr-10 font-mono text-xs"
                placeholder="sk-…"
                value={provider.api_key ?? ""}
                onChange={(e) => set({ api_key: e.target.value })}
              />
              <button
                type="button"
                onClick={() => setShowKey((v) => !v)}
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-slate-400 hover:text-slate-700"
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
              className="field"
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
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
              <option value="__custom__">Custom model ID (type below)</option>
            </select>
            <span className="mt-1.5 block text-[11.5px] leading-relaxed text-slate-500">
              Presets are convenience defaults, not availability guarantees. Type any
              custom Gemini model ID in the role fields below.
            </span>
          </Field>
        )}

        <div className="grid gap-4 sm:grid-cols-3">
          {ROLE_FIELDS.map((rf) => {
            const Icon = rf.icon;
            return (
              <div key={rf.key}>
                <div className="mb-1.5 flex items-center gap-1.5">
                  <Icon size={13} className="text-brand-600" />
                  <span className="text-[11px] font-bold uppercase tracking-wide text-slate-600">
                    {rf.label}
                  </span>
                </div>
                <input
                  type="text"
                  className="field font-mono text-xs"
                  placeholder={`${rf.key.replace("_model", "")} model id`}
                  value={provider[rf.key] ?? ""}
                  onChange={(e) => set({ [rf.key]: e.target.value })}
                />
                <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
                  {rf.purpose}
                </p>
              </div>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4">
          <button
            type="button"
            onClick={() => onTest(["red", "judge", "tuning"])}
            disabled={!canTest}
            className="btn-primary py-2"
          >
            {testState.status === "testing" ? (
              <>
                <Loader2 size={15} className="animate-spin" /> Testing…
              </>
            ) : (
              <>
                <Activity size={15} /> Test provider connection
              </>
            )}
          </button>
          <span className="text-[12px] text-slate-500">
            Sends a tiny structured-JSON probe to each model. Proves the API/model
            actually responds — no assessment is run.
          </span>
        </div>

        <p className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-[12px] leading-relaxed text-slate-600">
          <Lock size={14} className="mt-0.5 shrink-0 text-emerald-600" />
          <span>
            API key is used for this run only. It is{" "}
            <strong className="text-slate-800">
              not stored in browser storage, reports, or audit export
            </strong>
            , and is sent only with the current{" "}
            <code className="font-mono">/api/assessments/run</code> or{" "}
            <code className="font-mono">/api/providers/test</code> request.
          </span>
        </p>
      </div>

      <Diagnostics testState={testState} />
    </div>
  );
}
