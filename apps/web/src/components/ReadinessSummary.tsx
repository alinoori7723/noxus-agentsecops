import clsx from "clsx";
import type { ReadinessSummary as Summary, ChipColor } from "../types/noxus";
import { StatusChip } from "./StatusChip";

const VERDICT_BG: Record<ChipColor, string> = {
  green: "border-emerald-200 bg-emerald-50",
  amber: "border-amber-200 bg-amber-50",
  red: "border-rose-200 bg-rose-50",
  blue: "border-sky-200 bg-sky-50",
  neutral: "border-slate-200 bg-slate-50",
};

const VERDICT_BAR: Record<ChipColor, string> = {
  green: "bg-emerald-500",
  amber: "bg-amber-500",
  red: "bg-rose-500",
  blue: "bg-sky-500",
  neutral: "bg-slate-400",
};

const TOP_BORDER: Record<ChipColor, string> = {
  green: "border-t-emerald-400",
  amber: "border-t-amber-400",
  red: "border-t-rose-400",
  blue: "border-t-sky-400",
  neutral: "border-t-slate-300",
};

function Metric({
  label,
  value,
  detail,
  color,
}: {
  label: string;
  value: string;
  detail: string;
  color: ChipColor;
}) {
  return (
    <div className={clsx("card border-t-2 p-4", TOP_BORDER[color])}>
      <div className="kicker">{label}</div>
      <div className="mt-1.5 text-2xl font-black text-slate-900">{value}</div>
      <div className="mt-0.5 text-xs text-slate-500">{detail}</div>
    </div>
  );
}

export function ReadinessSummary({ model }: { model: Summary }) {
  const { badge } = model;
  return (
    <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
      <div
        className={clsx(
          "card relative overflow-hidden p-6 pl-7",
          VERDICT_BG[badge.color],
        )}
      >
        <span
          className={clsx(
            "absolute inset-y-0 left-0 w-1.5",
            VERDICT_BAR[badge.color],
          )}
        />
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip
            label={`Readiness gate: ${model.readiness_gate}`}
            color={badge.color}
            mono
          />
          <StatusChip label={badge.state} color={badge.color} mono />
        </div>
        <h3 className="mt-3 text-2xl font-black leading-tight text-slate-900">
          {badge.headline}
        </h3>
        <p className="mt-2.5 max-w-2xl text-sm leading-relaxed text-slate-600">
          {badge.explanation}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <StatusChip
            label={`Risk remaining: ${model.risk_level}`}
            color={model.risk_color}
          />
          <StatusChip label={`mode: ${model.mode}`} color="neutral" />
          <StatusChip
            label={`tuning iterations: ${model.tuning_iterations}`}
            color="neutral"
          />
        </div>
        {model.gate_blocked_explanation && (
          <p className="mt-3 text-xs font-semibold text-amber-700">
            {model.gate_blocked_explanation}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Metric
          label={model.before_score_label}
          value={`${model.before_score}/100`}
          detail={`${model.before_summary.failed_probes} failed probes`}
          color={model.before_summary.failed_probes ? "amber" : "green"}
        />
        <Metric
          label={model.after_score_label}
          value={`${model.after_score}/100`}
          detail={`delta ${model.score_delta >= 0 ? "+" : ""}${model.score_delta}`}
          color={badge.color}
        />
        <Metric
          label="Remediation progress"
          value={`${model.remediation_progress.resolved} / ${model.remediation_progress.unresolved}`}
          detail="resolved / unresolved findings"
          color={model.remediation_progress.resolved ? "green" : "neutral"}
        />
        <Metric
          label="Human review"
          value={String(model.human_review_count)}
          detail="required categories"
          color={model.human_review_count ? "amber" : "neutral"}
        />
      </div>
      {model.after_score_explanation && (
        <p className="col-span-2 -mt-1 text-xs font-medium text-amber-700">
          {model.after_score_explanation}
        </p>
      )}
      <p className="col-span-2 -mt-1 text-xs leading-relaxed text-slate-500">
        {model.readiness_score_explanation}
      </p>
    </div>
  );
}
