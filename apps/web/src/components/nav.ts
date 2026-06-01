import {
  LayoutDashboard,
  FileCog,
  PlayCircle,
  BarChart3,
  FileSearch,
  ShieldAlert,
  Plug,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export type SectionId =
  | "overview"
  | "target"
  | "assessment"
  | "results"
  | "evidence"
  | "risks"
  | "provider"
  | "proof";

export interface NavItem {
  id: SectionId;
  label: string;
  subtitle: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  {
    id: "overview",
    label: "Overview",
    subtitle: "Product positioning and the readiness loop",
    icon: LayoutDashboard,
  },
  {
    id: "target",
    label: "Target Config",
    subtitle: "System prompt, security policy, and business context",
    icon: FileCog,
  },
  {
    id: "assessment",
    label: "Assessment",
    subtitle: "Choose a mode and run the readiness loop",
    icon: PlayCircle,
  },
  {
    id: "results",
    label: "Results",
    subtitle: "Readiness verdict, audit timeline, and the Red/Blue cockpit",
    icon: BarChart3,
  },
  {
    id: "evidence",
    label: "Evidence",
    subtitle: "Findings with severity, detection mode, and remediation",
    icon: FileSearch,
  },
  {
    id: "risks",
    label: "Open Risks",
    subtitle: "Unresolved risk and human-review requirements",
    icon: ShieldAlert,
  },
  {
    id: "provider",
    label: "Provider Settings",
    subtitle: "Configure the Agent-Assisted LLM provider",
    icon: Plug,
  },
  {
    id: "proof",
    label: "Engineering Proof",
    subtitle: "Trust boundaries and implementation guarantees",
    icon: ShieldCheck,
  },
];
