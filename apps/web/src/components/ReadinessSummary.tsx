import clsx from "clsx";
import type { ReadinessSummary as Summary, ChipColor } from "../types/noxus";
import { SectionHeader } from "./Section";
import { StatusChip } from "./StatusChip";

const ACCENT_BAR: Record<ChipColor, string> = {
  green: "before:bg-emerald-400",
  amber: "before:bg-amber-400",
  red: "before:bg-rose-400",
  blue: "before:bg-sky-400",
  neutral: "before:bg-slate-400",
};

const TOP_BORDER: Record<ChipColor, string> = {
  green: "border-t-emerald-400/70",
  amber: "border-t-amber-400/70",
  red: "border-t-rose-400/70",
  blue: "border-t-sky-400/70",
  neutral: "border-t-slate-400/70",
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
    <div className={clsx("nx-card border-t-2 p-4", TOP_BORDER[color])}>
      <div className="nx-kicker">{label}</div>
      <div className="mt-1.5 text-2xl font-black text-white">{value}</div>
      <div className="mt-1 text-xs text-slate-400">{detail}</div>
    </div>
  );
}

export function ReadinessSummary({ model }: { model: Summary }) {
  const { badge } = model;
  return (
    <section>
      <SectionHeader
        kicker="Readiness summary"
        title="Final verdict"
        copy="Rendered directly from the generated report. Conditional results stay conditional — no cosmetic promotion to PASS."
      />
      <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
        <div
          className={clsx(
            "nx-panel relative overflow-hidden p-6 pl-7",
            "before:absolute before:inset-y-0 before:left-0 before:w-1.5",
            ACCENT_BAR[badge.color],
          )}
        >
          <StatusChip label={badge.state} color={badge.color} mono />
          <h3 className="mt-3 text-2xl font-black leading-tight text-white sm:text-3xl">
            {badge.headline}
          </h3>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-300">
            {badge.explanation}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <StatusChip label={`mode: ${model.mode}`} color="neutral" />
            <StatusChip
              label={`tuning iterations: ${model.tuning_iterations}`}
              color="neutral"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Metric
            label="Before score"
            value={`${model.before_score}/100`}
            detail={`${model.before_summary.failed_probes} failed probes`}
            color={model.before_summary.failed_probes ? "red" : "green"}
          />
          <Metric
            label="After score"
            value={`${model.after_score}/100`}
            detail={`delta ${model.score_delta >= 0 ? "+" : ""}${model.score_delta}`}
            color={badge.color}
          />
          <Metric
            label="Open risks"
            value={String(model.open_risk_count)}
            detail="visible in report"
            color={model.open_risk_count ? "amber" : "green"}
          />
          <Metric
            label="Human review"
            value={String(model.human_review_count)}
            detail="required categories"
            color={model.human_review_count ? "amber" : "neutral"}
          />
        </div>
      </div>
    </section>
  );
}
