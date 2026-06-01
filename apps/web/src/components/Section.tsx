import type { ReactNode } from "react";

interface SectionHeaderProps {
  kicker?: string;
  title: string;
  copy?: string;
  right?: ReactNode;
}

/** A lightweight in-content heading used at the top of a card/sub-section. */
export function SectionHeader({ kicker, title, copy, right }: SectionHeaderProps) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        {kicker && <div className="kicker">{kicker}</div>}
        <h3 className="mt-1 text-base font-bold tracking-tight text-slate-900">
          {title}
        </h3>
        {copy && (
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-slate-500">
            {copy}
          </p>
        )}
      </div>
      {right}
    </div>
  );
}
