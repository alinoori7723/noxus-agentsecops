import { useState } from "react";
import clsx from "clsx";
import { FileText, ShieldHalf, BookOpen, Download, RotateCcw } from "lucide-react";
import { SectionHeader } from "./Section";

export interface TargetInputs {
  system_prompt: string;
  security_policy_yaml: string;
  business_context: string;
}

interface InputWorkspaceProps {
  value: TargetInputs;
  onChange: (next: TargetInputs) => void;
  onLoadSamples: () => void;
  onReset: () => void;
  samplesLoading: boolean;
}

type TabKey = keyof TargetInputs;

const TABS: { key: TabKey; label: string; icon: typeof FileText; mono: boolean }[] = [
  { key: "system_prompt", label: "System Prompt", icon: FileText, mono: false },
  { key: "security_policy_yaml", label: "Security Policy YAML", icon: ShieldHalf, mono: true },
  { key: "business_context", label: "Business Context", icon: BookOpen, mono: false },
];

function lineCount(text: string): number {
  return text ? text.split("\n").length : 0;
}

export function InputWorkspace({
  value,
  onChange,
  onLoadSamples,
  onReset,
  samplesLoading,
}: InputWorkspaceProps) {
  const [active, setActive] = useState<TabKey>("system_prompt");
  const current = value[active];

  return (
    <section>
      <SectionHeader
        kicker="Configuration workspace"
        title="Target inputs"
        copy="Edit the system prompt, security policy, and business context. Your edits stay in the browser session — nothing is auto-reset."
        right={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onLoadSamples}
              disabled={samplesLoading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-ink-850 px-3 py-2 text-xs font-bold text-slate-200 transition hover:border-accent/50 hover:bg-ink-800 disabled:opacity-50"
            >
              <Download size={14} /> Load samples
            </button>
            <button
              type="button"
              onClick={onReset}
              className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-transparent px-3 py-2 text-xs font-bold text-slate-400 transition hover:border-rose-500/40 hover:text-rose-300"
            >
              <RotateCcw size={14} /> Reset
            </button>
          </div>
        }
      />

      <div className="nx-panel overflow-hidden">
        <div className="flex flex-wrap gap-1 border-b border-line bg-ink-950/40 p-2">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const selected = active === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActive(tab.key)}
                className={clsx(
                  "inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-bold transition",
                  selected
                    ? "bg-ink-800 text-white shadow-glow"
                    : "text-slate-400 hover:bg-ink-850 hover:text-slate-200",
                )}
              >
                <Icon size={15} />
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="p-4 sm:p-5">
          {TABS.map((tab) => (
            <textarea
              key={tab.key}
              value={value[tab.key]}
              onChange={(e) => onChange({ ...value, [tab.key]: e.target.value })}
              spellCheck={false}
              aria-label={tab.label}
              className={clsx(
                "nx-input nx-scroll min-h-[340px]",
                active === tab.key ? "block" : "hidden",
                !tab.mono && "font-sans text-sm",
              )}
            />
          ))}
          <div className="mt-3 flex items-center justify-between text-[11px] font-medium text-slate-500">
            <span>
              {TABS.find((t) => t.key === active)?.label}
            </span>
            <span>
              {lineCount(current)} lines · {current.length.toLocaleString()} characters
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
