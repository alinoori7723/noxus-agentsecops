import { useState } from "react";
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Hero } from "../components/Hero";
import { ReadinessSummary } from "../components/ReadinessSummary";
import { OpenRisks } from "../components/OpenRisks";
import { RedBlueDashboard } from "../components/RedBlueDashboard";
import { ModeProviderPanel } from "../components/ModeProviderPanel";
import type { Mode, ProviderConfig } from "../types/noxus";
import {
  conditionalPassSummary,
  evidenceWithProprietaryRisk,
  redBlueWithRealRail,
} from "./fixtures";

describe("Hero", () => {
  it("renders the product name and scope honesty note", () => {
    render(<Hero />);
    expect(screen.getByText("Noxus AgentSecOps")).toBeInTheDocument();
    expect(screen.getByText(/Not a runtime firewall/i)).toBeInTheDocument();
  });
});

describe("ReadinessSummary", () => {
  it("shows CONDITIONAL_PASS honestly (not promoted to PASS)", () => {
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
    expect(
      screen.getByText(/CONDITIONAL_PASS, not fake PASS/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/proprietary_context_exposure/i).length).toBeGreaterThan(0);
  });
});

describe("RedBlueDashboard", () => {
  it("renders detection labels and the real safety-rail telemetry preview", () => {
    render(<RedBlueDashboard model={redBlueWithRealRail} />);
    expect(screen.getAllByText("[DETERMINISTIC SIMULATION]").length).toBeGreaterThan(0);
    expect(screen.getByText(/real telemetry/i)).toBeInTheDocument();
    expect(
      screen.getByText(/untrusted data/i),
    ).toBeInTheDocument();
  });
});

function ProviderHarness() {
  const [mode, setMode] = useState<Mode>("deterministic");
  const [provider, setProvider] = useState<ProviderConfig>({
    provider_type: "local_openai_compatible",
    base_url: "http://localhost:4000/v1",
    api_key: "",
  });
  return (
    <ModeProviderPanel
      mode={mode}
      onModeChange={setMode}
      provider={provider}
      onProviderChange={setProvider}
      onRun={() => {}}
      running={false}
      error={null}
    />
  );
}

describe("ModeProviderPanel", () => {
  it("hides provider config in deterministic mode and reveals a password API key in agent mode", () => {
    render(<ProviderHarness />);
    // Deterministic by default: no API key field yet.
    expect(screen.queryByLabelText(/Show API key/i)).not.toBeInTheDocument();
    // Switch to Agent-Assisted Mode.
    fireEvent.click(screen.getByText("Agent-Assisted Mode"));
    const toggle = screen.getByLabelText(/Show API key/i);
    expect(toggle).toBeInTheDocument();
    // The API key input is a password field by default.
    const keyInput = screen.getByPlaceholderText("sk-…") as HTMLInputElement;
    expect(keyInput.type).toBe("password");
  });
});
