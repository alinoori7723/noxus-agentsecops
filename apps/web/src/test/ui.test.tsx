import { useState } from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Overview } from "../components/Overview";
import { Sidebar } from "../components/Sidebar";
import { AssessmentPanel } from "../components/AssessmentPanel";
import {
  ProviderSettings,
  baseUrlError,
  BASE_URL_SCHEME_ERROR,
  type ProviderTestState,
} from "../components/ProviderSettings";
import { PolicyError } from "../components/PolicyError";
import type { PolicyErrorDetail } from "../types/noxus";
import { ReadinessSummary } from "../components/ReadinessSummary";
import { OpenRisks } from "../components/OpenRisks";
import { RedBlueDashboard } from "../components/RedBlueDashboard";
import { ReportSummary } from "../components/ReportSummary";
import { RoleObservability } from "../components/RoleObservability";
import { NAV_ITEMS, type SectionId } from "../components/nav";
import type { AgentRole, Mode, ProviderConfig } from "../types/noxus";
import {
  conditionalPassSummary,
  evidenceWithProprietaryRisk,
  redBlueWithRealRail,
  deterministicTrace,
  agentTrace,
  providerTestSuccess,
  providerTestFailure,
} from "./fixtures";

describe("Overview", () => {
  it("renders the product positioning and scope honesty", () => {
    render(<Overview onConfigure={() => {}} onRunDemo={() => {}} running={false} />);
    expect(screen.getByText("Noxus AgentSecOps")).toBeInTheDocument();
    expect(
      screen.getByText(/Pre-production AI security readiness testing/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Not a runtime firewall/i)).toBeInTheDocument();
    expect(screen.getByText("Configure Assessment")).toBeInTheDocument();
  });
});

describe("Sidebar", () => {
  it("renders all main navigation sections", () => {
    render(<Sidebar active="overview" onSelect={() => {}} hasResult={false} />);
    for (const item of NAV_ITEMS) {
      expect(screen.getByText(item.label)).toBeInTheDocument();
    }
    expect(screen.getByText("Pre-production readiness tester")).toBeInTheDocument();
  });

  it("invokes onSelect when a section is clicked", () => {
    let picked: SectionId | null = null;
    render(
      <Sidebar active="overview" onSelect={(id) => (picked = id)} hasResult={false} />,
    );
    fireEvent.click(screen.getByText("Provider Settings"));
    expect(picked).toBe("provider");
  });
});

function AssessmentHarness() {
  const [mode, setMode] = useState<Mode>("deterministic");
  return (
    <AssessmentPanel
      mode={mode}
      onModeChange={setMode}
      provider={{ provider_type: "local_openai_compatible", api_key: "" }}
      onGoToProvider={() => {}}
      onRun={() => {}}
      running={false}
      error={null}
      providerTestOk={false}
      providerTestStale={false}
      providerConfigError={null}
    />
  );
}

describe("AssessmentPanel", () => {
  it("defaults to Deterministic Mode", () => {
    render(<AssessmentHarness />);
    const det = screen.getByText("Deterministic Mode").closest("button")!;
    const agent = screen.getByText("Agent-Assisted Mode").closest("button")!;
    expect(det.getAttribute("aria-pressed")).toBe("true");
    expect(agent.getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByText(/No AI credentials required/i)).toBeInTheDocument();
  });
});

function ProviderHarness({
  type = "gemini_native" as ProviderConfig["provider_type"],
  testState = {
    status: "idle",
    response: null,
    error: null,
    stale: false,
  } as ProviderTestState,
  onTest = (_roles: AgentRole[]) => {},
}: {
  type?: ProviderConfig["provider_type"];
  testState?: ProviderTestState;
  onTest?: (roles: AgentRole[]) => void;
}) {
  const [provider, setProvider] = useState<ProviderConfig>({
    provider_type: type,
    api_key: "",
    red_model: "gemini-3.5-flash",
    judge_model: "gemini-3.5-flash",
    tuning_model: "gemini-3.1-pro-preview",
  });
  return (
    <ProviderSettings
      provider={provider}
      onChange={setProvider}
      testState={testState}
      onTest={onTest}
    />
  );
}

describe("ProviderSettings", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("renders Gemini presets and a password API key field", () => {
    render(<ProviderHarness />);
    const keyInput = screen.getByPlaceholderText("sk-…") as HTMLInputElement;
    expect(keyInput.type).toBe("password");
    expect(screen.getAllByText("gemini-3.5-flash").length).toBeGreaterThan(0);
    expect(screen.getByText("gemini-3.1-pro-preview")).toBeInTheDocument();
    expect(
      screen.getByText(/not stored in browser storage, reports, or audit export/i),
    ).toBeInTheDocument();
  });

  it("shows role explanations for Red/Judge/Tuning models", () => {
    render(<ProviderHarness />);
    expect(screen.getByText("Generates adversarial probes")).toBeInTheDocument();
    expect(screen.getByText("Reviews semantic violations")).toBeInTheDocument();
    expect(screen.getByText("Proposes schema-bound patches")).toBeInTheDocument();
  });

  it("renders the Test provider connection button", () => {
    render(<ProviderHarness />);
    expect(
      screen.getByRole("button", { name: /Test provider connection/i }),
    ).toBeInTheDocument();
  });

  it("renders a successful provider diagnostic result", () => {
    render(
      <ProviderHarness
        testState={{ status: "done", response: providerTestSuccess, error: null, stale: false }}
      />,
    );
    expect(screen.getByText(/Provider diagnostics/i)).toBeInTheDocument();
    expect(screen.getByText(/all models ok/i)).toBeInTheDocument();
    expect(screen.getAllByText(/schema contract ok/i).length).toBe(3);
  });

  it("renders a failed provider diagnostic result with a sanitized message", () => {
    render(
      <ProviderHarness
        type="openai_compatible"
        testState={{ status: "done", response: providerTestFailure, error: null, stale: false }}
      />,
    );
    expect(screen.getByText(/issues found/i)).toBeInTheDocument();
    expect(screen.getByText(/did not satisfy the red schema contract/i)).toBeInTheDocument();
  });

  it("does not persist the API key to web storage", () => {
    render(<ProviderHarness />);
    const keyInput = screen.getByPlaceholderText("sk-…");
    fireEvent.change(keyInput, { target: { value: "sk-SECRET-TEST-123" } });
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});

describe("RoleObservability", () => {
  it("shows LLM roles as not used / deterministic baseline in deterministic mode", () => {
    render(
      <RoleObservability trace={deterministicTrace} evidence={evidenceWithProprietaryRisk} />,
    );
    expect(screen.getByText("Red Team Agent")).toBeInTheDocument();
    expect(screen.getByText("Semantic Judge")).toBeInTheDocument();
    expect(screen.getByText("Policy Tuning Agent")).toBeInTheDocument();
    expect(screen.getByText("Deterministic Patch Engine")).toBeInTheDocument();
    expect(screen.getAllByText(/Deterministic baseline/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/not used/i).length).toBeGreaterThan(0);
  });

  it("shows model and provider source for each agent role in agent mode", () => {
    render(<RoleObservability trace={agentTrace} evidence={evidenceWithProprietaryRisk} />);
    expect(screen.getAllByText("gemini-3.5-flash").length).toBeGreaterThan(0);
    expect(screen.getByText("gemini-3.1-pro-preview")).toBeInTheDocument();
    expect(screen.getAllByText(/gemini_native/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("LLM").length).toBeGreaterThan(0);
  });
});

describe("ReadinessSummary", () => {
  it("shows CONDITIONAL_PASS honestly (amber, not promoted to PASS)", () => {
    render(<ReadinessSummary model={conditionalPassSummary} />);
    expect(
      screen.getByText(/CONDITIONAL_PASS — improved, but human review still required/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/rather than returning a fake PASS/i),
    ).toBeInTheDocument();
  });
});

describe("OpenRisks", () => {
  it("renders proprietary-context exposure as an unresolved open risk", () => {
    render(<OpenRisks model={evidenceWithProprietaryRisk} />);
    expect(
      screen.getByText(/Proprietary-context exposure is not auto-patched/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/CONDITIONAL_PASS, not fake PASS/i)).toBeInTheDocument();
    expect(
      screen.getAllByText(/proprietary_context_exposure/i).length,
    ).toBeGreaterThan(0);
  });
});

describe("RedBlueDashboard", () => {
  it("renders detection labels and real safety-rail telemetry (no placeholder)", () => {
    render(<RedBlueDashboard model={redBlueWithRealRail} />);
    expect(screen.getAllByText("[DETERMINISTIC SIMULATION]").length).toBeGreaterThan(0);
    expect(screen.getByText(/real telemetry/i)).toBeInTheDocument();
    expect(screen.getByText(/untrusted data/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/<critical safety rail clause>/i),
    ).not.toBeInTheDocument();
  });
});

describe("baseUrlError", () => {
  it("rejects a base URL without an http(s) scheme", () => {
    expect(
      baseUrlError({ provider_type: "local_openai_compatible", base_url: "localhost:4000/v1" }),
    ).toBe(BASE_URL_SCHEME_ERROR);
    expect(
      baseUrlError({ provider_type: "openai_compatible", base_url: "localhost:4000/v1" }),
    ).toBe(BASE_URL_SCHEME_ERROR);
  });

  it("accepts http/https, blank-local, and gemini (no base URL)", () => {
    expect(
      baseUrlError({ provider_type: "local_openai_compatible", base_url: "http://localhost:4000/v1" }),
    ).toBeNull();
    expect(baseUrlError({ provider_type: "local_openai_compatible", base_url: "" })).toBeNull();
    expect(baseUrlError({ provider_type: "gemini_native" })).toBeNull();
  });
});

describe("ProviderSettings base URL validation", () => {
  it("shows an inline error and disables Test (no call) when the scheme is missing", () => {
    const onTest = vi.fn();
    render(
      <ProviderSettings
        provider={{
          provider_type: "openai_compatible",
          base_url: "localhost:4000/v1",
          api_key: "k",
        }}
        onChange={() => {}}
        testState={{ status: "idle", response: null, error: null, stale: false }}
        onTest={onTest}
      />,
    );
    expect(screen.getByText(BASE_URL_SCHEME_ERROR)).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: /Test provider connection/i });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onTest).not.toHaveBeenCalled();
  });

  it("shows local + Docker helper examples when the base URL is valid", () => {
    render(
      <ProviderSettings
        provider={{ provider_type: "local_openai_compatible", base_url: "http://localhost:4000/v1", api_key: "k" }}
        onChange={() => {}}
        testState={{ status: "idle", response: null, error: null, stale: false }}
        onTest={() => {}}
      />,
    );
    expect(screen.getByText(/host\.docker\.internal:4000\/v1/i)).toBeInTheDocument();
  });
});

const policyDetail: PolicyErrorDetail = {
  message: "Security Policy YAML does not match the supported Noxus policy schema.",
  code: "policy_schema",
  unsupported_keys: ["unsupported_top", "sensitive_data.bogus_nested"],
  allowed_keys: ["sensitive_data", "prompt_injection", "output_policy", "human_review"],
  example_yaml: "sensitive_data:\n  block: []\n  mask: []\n",
};

describe("PolicyError", () => {
  it("renders a friendly validation message and the unsupported keys", () => {
    render(<PolicyError detail={policyDetail} onResetPolicy={() => {}} />);
    expect(
      screen.getByText(/does not match the supported Noxus policy schema/i),
    ).toBeInTheDocument();
    expect(screen.getByText("unsupported_top")).toBeInTheDocument();
    expect(screen.getByText("sensitive_data.bogus_nested")).toBeInTheDocument();
  });

  it("does not render a raw Pydantic URL or raw validation dump", () => {
    render(<PolicyError detail={policyDetail} onResetPolicy={() => {}} />);
    expect(screen.queryByText(/errors\.pydantic\.dev/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Extra inputs are not permitted/i)).not.toBeInTheDocument();
  });

  it("invokes onResetPolicy when Reset policy to sample is clicked", () => {
    const onReset = vi.fn();
    render(<PolicyError detail={policyDetail} onResetPolicy={onReset} />);
    fireEvent.click(screen.getByRole("button", { name: /Reset policy to sample/i }));
    expect(onReset).toHaveBeenCalledTimes(1);
  });
});

import { PartialRunBanner } from "../components/PartialRunBanner";
import { agentTracePartialFailure, schemaFailure } from "./fixtures";

describe("PartialRunBanner (HUMAN_REVIEW_REQUIRED partial)", () => {
  it("shows the failed agent stage and that the deterministic baseline is preserved", () => {
    render(<PartialRunBanner failure={schemaFailure} />);
    expect(screen.getByText(/Red Team Agent failed/i)).toBeInTheDocument();
    expect(screen.getByText(/HUMAN_REVIEW_REQUIRED/)).toBeInTheDocument();
    expect(
      screen.getByText(/deterministic baseline.*completed/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/5 probes, 6 findings/)).toBeInTheDocument();
  });

  it("keeps the sanitized excerpt collapsed and free of API keys", () => {
    const withFakeKey = { ...schemaFailure, debug_excerpt: "garbage Bearer ***REDACTED*** tail" };
    render(<PartialRunBanner failure={withFakeKey} />);
    // Collapsed by default.
    expect(screen.queryByText(/garbage Bearer/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/Schema contract failure details/i));
    expect(screen.getByText(/garbage Bearer \*\*\*REDACTED\*\*\* tail/)).toBeInTheDocument();
    expect(screen.queryByText(/sk-[A-Za-z0-9]/)).not.toBeInTheDocument();
  });
});

describe("RoleObservability partial failure", () => {
  it("marks the failed agent role as failed", () => {
    render(
      <RoleObservability trace={agentTracePartialFailure} evidence={evidenceWithProprietaryRisk} />,
    );
    expect(screen.getByText("Red Team Agent")).toBeInTheDocument();
    expect(screen.getAllByText(/failed/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/not used/i).length).toBeGreaterThan(0);
  });
});

describe("Provider diagnostics role-vs-generic distinction", () => {
  it("shows a role schema contract failure, not a generic JSON success", () => {
    render(
      <ProviderHarness
        type="openai_compatible"
        testState={{ status: "done", response: providerTestFailure, error: null, stale: false }}
      />,
    );
    expect(screen.getByText(/schema contract failed/i)).toBeInTheDocument();
    expect(
      screen.getByText(/did not satisfy the red schema contract/i),
    ).toBeInTheDocument();
  });

  it("shows a role schema contract success", () => {
    render(
      <ProviderHarness
        testState={{ status: "done", response: providerTestSuccess, error: null, stale: false }}
      />,
    );
    expect(screen.getAllByText(/schema contract ok/i).length).toBe(3);
  });
});

import { RedTeamFallbackNotice } from "../components/RedTeamFallbackNotice";
import { AuditTimeline } from "../components/AuditTimeline";
import {
  agentTraceRedFallbackContinued,
  redTeamFailureContinued,
  redBlueNoPatch,
  baselineTimeline,
} from "./fixtures";

describe("RedTeamFallbackNotice (Red failed, continued on baseline)", () => {
  it("shows the fallback message and that baseline evidence was used", () => {
    render(<RedTeamFallbackNotice failure={redTeamFailureContinued} />);
    expect(
      screen.getByText(
        /Red Team Agent failed schema validation\. Noxus continued using deterministic baseline evidence/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/FALLBACK USED/)).toBeInTheDocument();
    expect(screen.getByText(/5 probes, 6 findings/)).toBeInTheDocument();
    // Distinct from a clean success: it is not labeled HUMAN_REVIEW_REQUIRED.
    expect(screen.queryByText(/HUMAN_REVIEW_REQUIRED/)).not.toBeInTheDocument();
  });

  it("keeps the sanitized excerpt collapsed and free of API keys", () => {
    const withFakeKey = {
      ...redTeamFailureContinued,
      debug_excerpt: "garbage Bearer ***REDACTED*** tail",
    };
    render(<RedTeamFallbackNotice failure={withFakeKey} />);
    expect(screen.queryByText(/garbage Bearer/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/Red Team schema failure details/i));
    expect(
      screen.getByText(/garbage Bearer \*\*\*REDACTED\*\*\* tail/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/sk-[A-Za-z0-9]/)).not.toBeInTheDocument();
  });
});

describe("RoleObservability after Red failure + fallback", () => {
  it("shows Red failed, judge skipped, tuning used, and the fallback note", () => {
    render(
      <RoleObservability
        trace={agentTraceRedFallbackContinued}
        evidence={evidenceWithProprietaryRisk}
      />,
    );
    expect(screen.getByText("Red Team Agent")).toBeInTheDocument();
    expect(screen.getAllByText(/failed/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/skipped/i).length).toBeGreaterThan(0);
    // Tuning Agent is shown as used because the loop continued.
    expect(screen.getAllByText(/^used$/i).length).toBeGreaterThan(0);
    // The fallback message explains the deterministic-baseline continuation.
    expect(
      screen.getAllByText(/continued using\s+deterministic baseline evidence/i)
        .length,
    ).toBeGreaterThan(0);
  });
});

describe("AuditTimeline (baseline preserved)", () => {
  it("is not blank when the deterministic baseline exists", () => {
    render(<AuditTimeline steps={baselineTimeline} />);
    expect(screen.getByText("Baseline probes")).toBeInTheDocument();
    // Real evidence counts are rendered (not a blank/zeroed timeline).
    expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/evidence items/i).length).toBe(
      baselineTimeline.length,
    );
  });
});

describe("RedBlueDashboard safety-rail honesty", () => {
  it("shows no fake safety rail preview when no patch was applied", () => {
    render(<RedBlueDashboard model={redBlueNoPatch} />);
    expect(
      screen.getByText(/No safety rail preview available from report data/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/real telemetry/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/<critical safety rail clause>/i),
    ).not.toBeInTheDocument();
  });

  it("shows the safety rail preview only when real patch telemetry exists", () => {
    render(<RedBlueDashboard model={redBlueWithRealRail} />);
    expect(screen.getByText(/real telemetry/i)).toBeInTheDocument();
    expect(screen.getByText(/untrusted data/i)).toBeInTheDocument();
  });
});

import {
  agentTraceJudgeDegraded,
} from "./fixtures";

describe("Evidence basis (degraded/fallback clarity)", () => {
  it("ui_shows_evidence_basis_for_fallback_run", () => {
    render(
      <RoleObservability
        trace={agentTraceRedFallbackContinued}
        evidence={evidenceWithProprietaryRisk}
      />,
    );
    expect(
      screen.getByText(/Evidence basis: deterministic baseline fallback/i),
    ).toBeInTheDocument();
  });

  it("normal_agent_run_does_not_show_fallback_basis", () => {
    render(
      <RoleObservability trace={agentTrace} evidence={evidenceWithProprietaryRisk} />,
    );
    expect(
      screen.getByText(/Evidence basis: red-team augmented/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/deterministic baseline fallback/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/failed schema validation/i),
    ).not.toBeInTheDocument();
  });

  it("shows Semantic Judge failed + degraded note when the judge degraded", () => {
    render(
      <RoleObservability
        trace={agentTraceJudgeDegraded}
        evidence={evidenceWithProprietaryRisk}
      />,
    );
    // Judge is shown failed; the loop continued on deterministic evidence.
    expect(screen.getAllByText(/failed/i).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Semantic Judge failed schema validation/i),
    ).toBeInTheDocument();
    // Tuning is still shown as used (the loop continued).
    expect(screen.getAllByText(/^used$/i).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Evidence basis: red-team augmented/i),
    ).toBeInTheDocument();
  });
});

import { redBlueZeroAfterScore } from "./fixtures";

describe("RedBlueDashboard remediation honesty (resolved vs unresolved)", () => {
  it("patch_operations_show_source_finding_ids", () => {
    render(<RedBlueDashboard model={redBlueWithRealRail} />);
    expect(
      screen.getByText(/probe_indirect_prompt_injection:indirect_prompt_injection_simulated/),
    ).toBeInTheDocument();
  });

  it("no_source_finding_not_specified_text", () => {
    render(<RedBlueDashboard model={redBlueWithRealRail} />);
    expect(screen.queryByText(/not specified/i)).not.toBeInTheDocument();
  });

  it("ui_shows_resolved_and_unresolved_counts", () => {
    render(<RedBlueDashboard model={redBlueWithRealRail} />);
    expect(screen.getByText(/resolved findings: 5/i)).toBeInTheDocument();
    expect(screen.getByText(/unresolved findings: 1/i)).toBeInTheDocument();
  });

  it("ui_explains_zero_after_score_when_patches_applied", () => {
    render(<RedBlueDashboard model={redBlueZeroAfterScore} />);
    expect(
      screen.getByText(/Patches were applied, but blocking findings remained in retest/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/refused to mark this target safe/i)).toBeInTheDocument();
    // Rejected/unlinked proposal is shown and labeled as not applied.
    expect(screen.getByText(/Rejected \/ unlinked proposals/i)).toBeInTheDocument();
    expect(screen.getAllByText(/rejected · unlinked/i).length).toBeGreaterThan(0);
  });

  it("human_review_categories_render_from_unresolved_findings", () => {
    render(<RedBlueDashboard model={redBlueWithRealRail} />);
    expect(screen.getByText("proprietary_context")).toBeInTheDocument();
  });

  it("no_fake_pass_when_unresolved_findings_remain", () => {
    render(<RedBlueDashboard model={redBlueZeroAfterScore} />);
    // Unresolved risk is surfaced; no "primary resolved" success for the patch.
    expect(screen.getByText(/unresolved findings: 9/i)).toBeInTheDocument();
    expect(screen.getByText(/applied · primary unresolved/i)).toBeInTheDocument();
    expect(screen.queryByText(/· primary resolved/i)).not.toBeInTheDocument();
  });
});

import { conditionalReportSummary } from "./fixtures";

describe("ReadinessSummary readiness-gate vs remediation-progress (Fix 1)", () => {
  it("ui_labels_after_score_as_readiness_gate_score", () => {
    render(<ReadinessSummary model={conditionalPassSummary} />);
    expect(screen.getByText("Readiness gate score")).toBeInTheDocument();
    expect(screen.getByText(/Readiness gate: CONDITIONAL/i)).toBeInTheDocument();
  });

  it("ui_shows_remediation_progress_next_to_score", () => {
    render(<ReadinessSummary model={conditionalPassSummary} />);
    expect(screen.getByText("Remediation progress")).toBeInTheDocument();
    expect(screen.getByText("5 / 1")).toBeInTheDocument();
    expect(screen.getByText("resolved / unresolved findings")).toBeInTheDocument();
  });

  it("ui_explains_zero_after_score_when_resolved_findings_exist", () => {
    const zeroGate = {
      ...conditionalPassSummary,
      readiness_gate: "BLOCKED",
      after_score: 0,
      after_score_explanation:
        "Readiness remains blocked because high-risk findings remain. Remediation progress is shown separately.",
    };
    render(<ReadinessSummary model={zeroGate} />);
    expect(
      screen.getByText(/Readiness remains blocked because high-risk findings remain/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Remediation progress is shown separately/i)).toBeInTheDocument();
  });
});

describe("RedBlueDashboard primary lineage + derivation (Fix 2 & 3)", () => {
  it("ui_shows_primary_source_before_secondary_sources", () => {
    render(<RedBlueDashboard model={redBlueWithRealRail} />);
    expect(screen.getByText(/Primary source:/i)).toBeInTheDocument();
    expect(
      screen.getByText("probe_indirect_prompt_injection:indirect_prompt_injection_simulated"),
    ).toBeInTheDocument();
  });

  it("ui_renders_human_review_derivation", () => {
    render(<RedBlueDashboard model={redBlueWithRealRail} />);
    expect(
      screen.getByText(/Human review requirements \(derived from unresolved findings\)/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/derived from retest/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Derived from 1 unresolved retest finding/i),
    ).toBeInTheDocument();
  });

  it("ui_separates_readiness_gate_from_remediation_progress", () => {
    render(<RedBlueDashboard model={redBlueZeroAfterScore} />);
    expect(screen.getByText(/readiness gate: BLOCKED/i)).toBeInTheDocument();
    expect(screen.getByText(/readiness gate score: 0\/100/i)).toBeInTheDocument();
    expect(screen.getByText(/remediation progress: 0 resolved \/ 9 unresolved/i)).toBeInTheDocument();
  });
});

describe("ReportSummary judge-safe summary (Fix 4)", () => {
  it("report_summary_lists_resolved_and_unresolved_types", () => {
    render(<ReportSummary model={conditionalReportSummary} />);
    expect(screen.getByText("What improved")).toBeInTheDocument();
    expect(screen.getByText("pii_leakage")).toBeInTheDocument();
    expect(screen.getByText("What remains blocked")).toBeInTheDocument();
    expect(screen.getByText("must_not_appear_violation")).toBeInTheDocument();
  });

  it("report_summary_explains_no_pass_with_demo_copy", () => {
    render(<ReportSummary model={conditionalReportSummary} />);
    expect(
      screen.getByText(/Noxus did not mark this target safe/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Final state is not PASS because unsupported or unresolved/i),
    ).toBeInTheDocument();
  });

  it("ui_does_not_present_patch_count_as_success_count", () => {
    render(<ReportSummary model={conditionalReportSummary} />);
    // The "what improved" count is the RESOLVED-finding count (5), not a patch count.
    expect(screen.getByText(/5 resolved finding/i)).toBeInTheDocument();
  });
});

import { TimeoutNotice } from "../components/TimeoutNotice";
import {
  tuningTimeoutFailure,
  recoveredTuningFallback,
  providerTestTimeout,
} from "./fixtures";

describe("TimeoutNotice role-specific LLM timeout (Fix 1 & 4)", () => {
  it("ui_renders_role_specific_timeout_message", () => {
    render(<TimeoutNotice failure={tuningTimeoutFailure} fallback={null} />);
    expect(
      screen.getByText(/timed out during Policy Tuning Agent using gemini-3.1-pro-preview/i),
    ).toBeInTheDocument();
    // Role, model, and retry count are surfaced (no generic-only message).
    expect(screen.getAllByText(/Policy Tuning Agent/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Retries: 2/)).toBeInTheDocument();
  });

  it("renders the tuning fallback note (fallback does not hide the timeout)", () => {
    render(
      <TimeoutNotice failure={null} fallback={recoveredTuningFallback} />,
    );
    expect(
      screen.getByText(/timed out on/i),
    ).toBeInTheDocument();
    expect(screen.getByText("gemini-3.1-pro-preview")).toBeInTheDocument();
    expect(screen.getByText("gemini-3.5-flash")).toBeInTheDocument();
  });

  it("renders nothing when there is no timeout or fallback", () => {
    const { container } = render(<TimeoutNotice failure={null} fallback={null} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("Provider diagnostics timeout vs schema failure (Fix 6)", () => {
  it("provider_test_distinguishes_timeout_from_schema_failure_in_ui", () => {
    render(
      <ProviderHarness
        type="gemini_native"
        testState={{ status: "done", response: providerTestTimeout, error: null, stale: false }}
      />,
    );
    // The timed-out role shows a distinct "timed out" chip, not "schema failed".
    expect(screen.getAllByText(/^timed out$/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/schema contract failed/i)).toBeInTheDocument();
    expect(screen.getByText(/timed out after 60s/i)).toBeInTheDocument();
  });
});

describe("ReadinessSummary readiness-score, not risk-score (KPI Fix 1)", () => {
  it("ui_does_not_label_readiness_as_risk_score", () => {
    render(<ReadinessSummary model={conditionalPassSummary} />);
    // The baseline higher-is-better score is a READINESS score, not a risk score.
    expect(screen.getByText("Baseline readiness score")).toBeInTheDocument();
    expect(screen.queryByText(/risk score/i)).not.toBeInTheDocument();
    // Remaining risk is shown as a qualitative level, not a 0/100 number.
    expect(screen.getByText(/Risk remaining: Medium/i)).toBeInTheDocument();
  });

  it("report_summary_explains_readiness_score_direction", () => {
    render(<ReadinessSummary model={conditionalPassSummary} />);
    expect(screen.getByText(/Higher is safer/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Risk is represented separately/i),
    ).toBeInTheDocument();
  });
});

describe("RedBlueDashboard related findings + probe mapping (KPI Fix 3 & 4)", () => {
  it("ui_uses_related_findings_not_secondary_sources_for_non_primary_lineage", () => {
    const model = {
      ...redBlueWithRealRail,
      blue: {
        ...redBlueWithRealRail.blue,
        patches: [
          {
            ...redBlueWithRealRail.blue.patches[0],
            related_finding_groups: {
              same_category_related: [
                "probe_indirect_prompt_injection:indirect_prompt_injection",
              ],
              leakage_from_same_probe: [],
              generic_policy_related: [],
            },
          },
        ],
      },
    };
    render(<RedBlueDashboard model={model} />);
    expect(
      screen.getByText(/Related findings from same category:/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Secondary sources/i)).not.toBeInTheDocument();
  });

  it("ui_related_findings_labels_are_causal_not_generic", () => {
    const model = {
      ...redBlueWithRealRail,
      blue: {
        ...redBlueWithRealRail.blue,
        patches: [
          {
            ...redBlueWithRealRail.blue.patches[0],
            related_finding_groups: {
              same_category_related: [],
              leakage_from_same_probe: [
                "probe_indirect_prompt_injection:customer_identifier_leakage",
              ],
              generic_policy_related: [],
            },
          },
        ],
      },
    };
    render(<RedBlueDashboard model={model} />);
    // Causal label, not a generic "related findings" dump.
    expect(screen.getByText(/Leakage from same probe:/i)).toBeInTheDocument();
  });

  it("ui_shows_probe_finding_mapping_matrix", () => {
    render(<RedBlueDashboard model={redBlueWithRealRail} />);
    expect(screen.getByText(/Probe \/ finding mapping matrix/i)).toBeInTheDocument();
    expect(
      screen.getByText(/one probe may emit multiple findings/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Baseline: 5 failed probes -> 6 finding instances/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Retest: 1 failed probes -> 1 unresolved finding instances/i),
    ).toBeInTheDocument();
  });

  it("ui_does_not_say_findings_when_it_means_finding_types", () => {
    render(<RedBlueDashboard model={redBlueWithRealRail} />);
    // The matrix distinguishes finding INSTANCES from finding TYPES.
    expect(screen.getByText(/finding type\(s\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Unresolved types:/i)).toBeInTheDocument();
  });
});

describe("ReadinessSummary higher-is-better is not a risk score (final reporting)", () => {
  it("no_risk_score_label_for_higher_is_better_score", () => {
    render(<ReadinessSummary model={conditionalPassSummary} />);
    expect(screen.queryByText(/risk score/i)).not.toBeInTheDocument();
    expect(screen.getByText("Baseline readiness score")).toBeInTheDocument();
  });
});

describe("RedBlueDashboard BLOCKED gate + positive delta (KPI Fix 5)", () => {
  it("ui_does_not_present_positive_delta_as_pass", () => {
    render(<RedBlueDashboard model={redBlueZeroAfterScore} />);
    expect(
      screen.getByText(
        /Readiness improved, but deployment remains blocked because unresolved high-risk findings remain/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Gate remains blocked/i)).toBeInTheDocument();
    // The readiness gate is BLOCKED, never promoted to PASS.
    expect(screen.queryByText(/\bPASS\b/)).not.toBeInTheDocument();
  });
});
