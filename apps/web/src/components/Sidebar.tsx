import clsx from "clsx";
import { ShieldCheck } from "lucide-react";
import { NAV_ITEMS, type SectionId } from "./nav";

interface SidebarProps {
  active: SectionId;
  onSelect: (id: SectionId) => void;
  hasResult: boolean;
}

export function Sidebar({ active, onSelect, hasResult }: SidebarProps) {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-2.5 border-b border-slate-200 px-5 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white">
          <ShieldCheck size={19} strokeWidth={2.3} />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-extrabold tracking-tight text-slate-900">
            Noxus
          </div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-brand-600">
            AgentSecOps
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = active === item.id;
          const showDot = item.id === "results" && hasResult;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              aria-current={isActive ? "page" : undefined}
              className={clsx("nav-item", isActive && "nav-item-active")}
            >
              <Icon size={17} className={isActive ? "text-brand-600" : "text-slate-400"} />
              <span className="flex-1 text-left">{item.label}</span>
              {showDot && (
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" title="Results ready" />
              )}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-slate-200 px-5 py-3.5">
        <div className="flex items-center gap-2 text-[11px] font-medium text-slate-500">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Pre-production readiness tester
        </div>
      </div>
    </aside>
  );
}
