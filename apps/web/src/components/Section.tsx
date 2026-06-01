import type { ReactNode } from "react";

interface SectionHeaderProps {
  kicker: string;
  title: string;
  copy?: string;
  right?: ReactNode;
}

export function SectionHeader({ kicker, title, copy, right }: SectionHeaderProps) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <div className="nx-kicker">{kicker}</div>
        <h2 className="mt-1 text-xl font-extrabold tracking-tight text-white sm:text-2xl">
          {title}
        </h2>
        {copy && (
          <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-slate-400">
            {copy}
          </p>
        )}
      </div>
      {right}
    </div>
  );
}
