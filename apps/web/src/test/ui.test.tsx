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
