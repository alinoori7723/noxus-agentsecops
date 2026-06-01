import { Swords, Gavel, Wrench, Cog } from "lucide-react";
import type {
  AgentTrace,
  AgentTraceStage,
  ChipColor,
  EvidenceModel,
  StageStatus,
} from "../types/noxus";
import { SectionHeader } from "./Section";
import { StatusChip } from "./StatusChip";

const STATUS_COLOR: Record<StageStatus, ChipColor> = {
  used: "green",
  not_used: "neutral",
  failed: "red",
  human_review_required: "amber",
};

const STATUS_LABEL: Record<StageStatus, string> = {
  used: "used",
  not_used: "not used",
  failed: "failed",
  human_review_required: "human review",
};

const STAGE_META: Record<
  string,
  { title: string; role: string; icon: typeof Swords; isEngine?: boolean }
> = {
  red_team: { title: "Red Team Agent", role: "Generated structured probes", icon: Swords },
  semantic_judge: {
    title: "Semantic Judge",
    role: "Evaluated semantic violations",
    icon: Gavel,
  },
  policy_tuning: {
    title: "Policy Tuning Agent",
    role: "Proposed schema-bound PatchSet",
    icon: Wrench,
  },
  patch_application: {
    title: "Deterministic Patch Engine",
    role: "Applied allowed patches",
    icon: Cog,
    isEngine: true,
  },
};

function sourceLabel(source: string): string {
  return (
    {
      llm: "LLM",
      deterministic_baseline: "Deterministic baseline",
      deterministic: "Deterministic",
      deterministic_mapper: "Deterministic mapper",
      deterministic_engine: "Deterministic engine",
    }[source] ?? source
  );
}

function RoleCard({
  stage,
  judgeConfidence,
}: {
  stage: AgentTraceStage;
  judgeConfidence?: string | null;
}) {
  const meta = STAGE_META[stage.stage];
  if (!meta) return null;
  const Icon = meta.icon;
  const engine = meta.isEngine;
  return (
    <div
      className={
        "card p-4 " +
        (engine ? "border-slate-300 bg-slate-50/80" : "")
      }
    >
      <div className="flex items-start gap-2.5">
        <div
          className={
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg " +
            (engine ? "bg-slate-200 text-slate-700" : "bg-brand-50 text-brand-600")
          }
        >
          <Icon size={18} />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-[13px] font-bold text-slate-900">{meta.title}</h4>
            <StatusChip
              label={STATUS_LABEL[stage.status]}
              color={STATUS_COLOR[stage.status]}
            />
          </div>
          <p className="mt-0.5 text-[12px] text-slate-500">{meta.role}</p>
        </div>
      </div>

      <dl className="mt-3 space-y-1 text-[12px]">
        {!engine && (
          <div className="flex justify-between gap-2">
            <dt className="text-slate-400">Provider</dt>
            <dd className="font-medium text-slate-700">
              {stage.provider_type ?? "—"}
            </dd>
          </div>
        )}
        {!engine && (
          <div className="flex justify-between gap-2">
            <dt className="text-slate-400">Model</dt>
            <dd className="truncate font-mono text-[11px] text-slate-700">
              {stage.model ?? "—"}
            </dd>
          </div>
        )}
        <div className="flex justify-between gap-2">
          <dt className="text-slate-400">Source</dt>
          <dd className="font-medium text-slate-700">{sourceLabel(stage.source)}</dd>
        </div>
        {stage.stage === "semantic_judge" && judgeConfidence && (
          <div className="flex justify-between gap-2">
            <dt className="text-slate-400">Confidence</dt>
            <dd className="font-medium text-slate-700">{judgeConfidence}</dd>
          </div>
        )}
      </dl>
      <p className="mt-2.5 border-t border-slate-100 pt-2 text-[11.5px] leading-relaxed text-slate-500">
        {stage.summary}
      </p>
    </div>
  );
}

export function RoleObservability({
  trace,
  evidence,
}: {
  trace: AgentTrace;
  evidence: EvidenceModel;
}) {
  const judgeConfidence =
    evidence.findings.find((f) => f.detection_mode === "semantic_llm")?.confidence ??
    null;
  const order = ["red_team", "semantic_judge", "policy_tuning", "patch_application"];
  const stages = order
    .map((id) => trace.stages.find((s) => s.stage === id))
    .filter(Boolean) as AgentTraceStage[];

  return (
    <div className="card p-5">
      <SectionHeader
        kicker="LLM role observability"
        title="Which model did what"
        copy={
          trace.execution_mode === "agent_assisted"
            ? `Agent-Assisted run via ${trace.provider_type}. Each LLM role and the deterministic engine are shown separately.`
            : "Deterministic run — no live LLM calls. The deterministic baseline and patch engine did the work; LLM roles were not used."
        }
        right={
          <StatusChip
            label={
              trace.execution_mode === "agent_assisted"
                ? "agent-assisted"
                : "deterministic"
            }
            color={trace.execution_mode === "agent_assisted" ? "blue" : "neutral"}
          />
        }
      />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {stages.map((s) => (
          <RoleCard key={s.stage} stage={s} judgeConfidence={judgeConfidence} />
        ))}
      </div>
    </div>
  );
}
