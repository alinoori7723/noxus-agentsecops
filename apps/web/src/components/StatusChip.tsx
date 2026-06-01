import clsx from "clsx";
import type { ChipColor } from "../types/noxus";

const CHIP_STYLES: Record<ChipColor, string> = {
  green: "border-emerald-500/40 bg-emerald-500/12 text-emerald-300",
  amber: "border-amber-500/40 bg-amber-500/12 text-amber-300",
  red: "border-rose-500/40 bg-rose-500/12 text-rose-300",
  blue: "border-sky-500/40 bg-sky-500/12 text-sky-300",
  neutral: "border-slate-600/50 bg-slate-600/15 text-slate-300",
};

export function chipClasses(color: ChipColor): string {
  return CHIP_STYLES[color] ?? CHIP_STYLES.neutral;
}

export interface StatusChipProps {
  label: string;
  color?: ChipColor;
  mono?: boolean;
  className?: string;
}

export function StatusChip({
  label,
  color = "neutral",
  mono = false,
  className,
}: StatusChipProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-bold leading-5",
        mono && "font-mono tracking-tight",
        chipClasses(color),
        className,
      )}
    >
      {label}
    </span>
  );
}
