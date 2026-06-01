import clsx from "clsx";
import type { ChipColor } from "../types/noxus";

const CHIP_STYLES: Record<ChipColor, string> = {
  green: "border-emerald-200 bg-emerald-50 text-emerald-700",
  amber: "border-amber-200 bg-amber-50 text-amber-700",
  red: "border-rose-200 bg-rose-50 text-rose-700",
  blue: "border-sky-200 bg-sky-50 text-sky-700",
  neutral: "border-slate-200 bg-slate-100 text-slate-600",
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
        "inline-flex items-center whitespace-nowrap rounded-md border px-2 py-0.5 text-[11px] font-semibold leading-5",
        mono && "font-mono tracking-tight",
        chipClasses(color),
        className,
      )}
    >
      {label}
    </span>
  );
}
