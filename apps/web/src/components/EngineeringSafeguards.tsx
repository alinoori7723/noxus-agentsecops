import {
  FileCheck2,
  Cog,
  RefreshCcw,
  UserCheck,
  ScanSearch,
  Container,
  FileJson,
  LayoutPanelTop,
  FlaskConical,
  type LucideIcon,
} from "lucide-react";
import type { SafeguardItem } from "../types/noxus";

// Honest, static trust points about the product's engineering. These render with
// or without a run; real backend-provided safeguards (when present) are merged in
// by title so nothing is duplicated or drifts.
const STATIC_SAFEGUARDS: { title: string; detail: string; icon: LucideIcon }[] = [
  {
    title: "Pydantic contracts",
    detail: "Every LLM output validates against strict schemas before entering the workflow.",
    icon: FileCheck2,
  },
  {
    title: "Deterministic patch engine",
    detail: "Agents propose; only the deterministic engine applies allowed prompt/policy changes.",
    icon: Cog,
  },
  {
    title: "One repair attempt max",
    detail: "A single schema-repair attempt is allowed; persistent failures fall back to human review.",
    icon: RefreshCcw,
  },
  {
    title: "HUMAN_REVIEW_REQUIRED fallback",
    detail: "Any unrecoverable schema-contract failure aborts LLM execution and returns a safe state.",
    icon: UserCheck,
  },
  {
    title: "AST / static scope guard",
    detail: "Static tests block forbidden cloud/provider SDK imports and product-scope creep.",
    icon: ScanSearch,
  },
  {
    title: "Non-root Docker runtime",
    detail: "The packaged container runs as a non-root user on python:3.11-slim.",
    icon: Container,
  },
  {
    title: "Local-only JSONL audit export",
    detail: "Opt-in, append-only newline JSON confined to a configured local directory.",
    icon: FileJson,
  },
  {
    title: "React SPA + FastAPI adapter",
    detail: "A light React/Tailwind cockpit served by a thin FastAPI API over the unchanged core.",
    icon: LayoutPanelTop,
  },
  {
    title: "Release verification: 430 Python + 51 frontend tests",
    detail: "Deterministic core, schema-bound agents, API adapter, and UI components are all tested.",
    icon: FlaskConical,
  },
];

export function EngineeringSafeguards({ items }: { items: SafeguardItem[] }) {
  // Prefer the real backend detail text when a run has provided it.
  const backendByTitle = new Map(items.map((i) => [i.title.toLowerCase(), i.detail]));
  const cards = STATIC_SAFEGUARDS.map((s) => {
    const backendDetail = backendByTitle.get(s.title.toLowerCase());
    return { ...s, detail: backendDetail ?? s.detail };
  });
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map(({ title, detail, icon: Icon }) => (
        <div key={title} className="card p-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
            <Icon size={18} />
          </div>
          <h4 className="mt-2.5 text-[13px] font-bold leading-snug text-slate-900">
            {title}
          </h4>
          <p className="mt-1 text-[12px] leading-relaxed text-slate-500">{detail}</p>
        </div>
      ))}
    </div>
  );
}
