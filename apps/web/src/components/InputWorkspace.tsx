import { useState } from "react";
import clsx from "clsx";
import { FileText, ShieldHalf, BookOpen, Download, RotateCcw } from "lucide-react";

export interface TargetInputs {
  system_prompt: string;
  security_policy_yaml: string;
  business_context: string;
}

interface InputWorkspaceProps {
  value: TargetInputs;
  onChange: (next: TargetInputs) => void;
  onLoadSamples: () => void;
  onResetTab: (key: keyof TargetInputs) => void;
  samplesLoading: boolean;
  loadedFromSample: boolean;
}

type TabKey = keyof TargetInputs;

const TABS: { key: TabKey; label: string; icon: typeof FileText; mono: boolean }[] = [
  { key: "system_prompt", label: "System Prompt", icon: FileText, mono: false },
  { key: "security_policy_yaml", label: "Security Policy YAML", icon: ShieldHalf, mono: true },
  { key: "business_context", label: "Business Context", icon: BookOpen, mono: false },
];

export function InputWorkspace({
  value,
  onChange,
  onLoadSamples,
  onResetTab,
  samplesLoading,
  loadedFromSample,
}: InputWorkspaceProps) {
  const [active, setActive] = useState<TabKey>("system_prompt");
  const current = value[active];
  const activeTab = TABS.find((t) => t.key === active)!;

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-50/70 px-3 py-2.5">
        <div className="flex flex-wrap gap-1">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const selected = active === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActive(tab.key)}
                className={clsx(
                  "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-semibold transition",
                  selected
                    ? "border border-slate-200 bg-white text-slate-900 shadow-card"
                    : "text-slate-500 hover:bg-white/70 hover:text-slate-800",
                )}
              >
                <Icon size={15} />
                {tab.label}
              </button>
            );
          })}
        </div>
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={onLoadSamples}
            disabled={samplesLoading}
            className="btn-ghost py-1.5 text-xs"
          >
            <Download size={14} /> Load Samples
          </button>
          <button
            type="button"
            onClick={() => onResetTab(active)}
            className="btn-ghost py-1.5 text-xs text-slate-500"
          >
            <RotateCcw size={14} /> Reset Current Tab
          </button>
        </div>
      </div>

      <div className="p-4 lg:p-5">
        <textarea
          key={active}
          value={current}
          onChange={(e) => onChange({ ...value, [active]: e.target.value })}
          spellCheck={false}
          aria-label={activeTab.label}
          className={clsx(
            "editor scroll-thin min-h-[360px]",
            !activeTab.mono && "font-sans",
          )}
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
          <span className="inline-flex items-center gap-2">
            {loadedFromSample && (
              <span className="inline-flex items-center gap-1 rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-medium">
                loaded from sample
              </span>
            )}
            <span>Edits persist in memory for this session.</span>
          </span>
          <span className="font-medium">
            {current.length.toLocaleString()} characters ·{" "}
            {current ? current.split("\n").length : 0} lines
          </span>
        </div>
      </div>
    </div>
  );
}
