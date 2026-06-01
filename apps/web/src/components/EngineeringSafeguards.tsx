import {
  FileCheck2,
  Cog,
  ScanSearch,
  Container,
  FileJson,
  RefreshCcw,
  UserCheck,
} from "lucide-react";
import type { SafeguardItem } from "../types/noxus";
import { SectionHeader } from "./Section";

// Static trust points the demo asserts about its own engineering. These augment
// the backend-provided safeguards with the bounded-loop / fallback guarantees.
const STATIC_SAFEGUARDS: { title: string; detail: string }[] = [
  {
    title: "One repair attempt max",
    detail:
      "A single schema-repair attempt is allowed; persistent failures fall back to human review.",
  },
  {
    title: "HUMAN_REVIEW_REQUIRED fallback",
    detail:
      "Any unrecoverable schema-contract failure aborts LLM execution and returns a safe state.",
  },
];

const ICONS = [FileCheck2, Cog, ScanSearch, Container, FileJson, RefreshCcw, UserCheck];

export function EngineeringSafeguards({ items }: { items: SafeguardItem[] }) {
  const combined = [
    ...items.map((i) => ({ title: i.title, detail: i.detail })),
    ...STATIC_SAFEGUARDS,
  ];
  return (
    <section>
      <SectionHeader
        kicker="Engineering safeguards"
        title="Trust boundaries"
        copy="Concise implementation proof points for reviewers evaluating product scope and safety."
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        {combined.map((item, i) => {
          const Icon = ICONS[i % ICONS.length];
          return (
            <div key={item.title} className="nx-card p-4">
              <Icon size={18} className="text-accent-soft" />
              <h3 className="mt-2.5 text-sm font-extrabold leading-snug text-white">
                {item.title}
              </h3>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
                {item.detail}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
