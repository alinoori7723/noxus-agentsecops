import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "./components/AppShell";
import { Hero } from "./components/Hero";
import { InputWorkspace, type TargetInputs } from "./components/InputWorkspace";
import { ModeProviderPanel } from "./components/ModeProviderPanel";
import { EmptyState } from "./components/EmptyState";
import { ReadinessSummary } from "./components/ReadinessSummary";
import { AuditTimeline } from "./components/AuditTimeline";
import { RedBlueDashboard } from "./components/RedBlueDashboard";
import { EvidenceReport } from "./components/EvidenceReport";
import { OpenRisks } from "./components/OpenRisks";
import { EngineeringSafeguards } from "./components/EngineeringSafeguards";
import {
  getHealth,
  getProof,
  getSampleInputs,
  runAssessment,
  ApiError,
} from "./api/client";
import type {
  AssessmentResponse,
  Mode,
  ProofIndicators,
  ProviderConfig,
} from "./types/noxus";

const EMPTY_INPUTS: TargetInputs = {
  system_prompt: "",
  security_policy_yaml: "",
  business_context: "",
};

const DEFAULT_PROVIDER: ProviderConfig = {
  provider_type: "local_openai_compatible",
  base_url: "http://localhost:4000/v1",
  api_key: "",
  red_model: "gemini-3.5-flash",
  judge_model: "gemini-3.5-flash",
  tuning_model: "gemini-3.1-pro-preview",
};

export default function App() {
  const [inputs, setInputs] = useState<TargetInputs>(EMPTY_INPUTS);
  const [mode, setMode] = useState<Mode>("deterministic");
  const [provider, setProvider] = useState<ProviderConfig>(DEFAULT_PROVIDER);

  const [proof, setProof] = useState<ProofIndicators | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [samplesLoading, setSamplesLoading] = useState(false);

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AssessmentResponse | null>(null);

  const resultsRef = useRef<HTMLDivElement>(null);

  const loadSamples = useCallback(async () => {
    setSamplesLoading(true);
    try {
      const s = await getSampleInputs();
      setInputs({
        system_prompt: s.system_prompt,
        security_policy_yaml: s.security_policy_yaml,
        business_context: s.business_context,
      });
    } catch {
      // leave inputs unchanged on failure
    } finally {
      setSamplesLoading(false);
    }
  }, []);

  // One-time bootstrap: health, proof chips, and initial sample inputs.
  useEffect(() => {
    getHealth()
      .then((h) => setOnline(Boolean(h.ok)))
      .catch(() => setOnline(false));
    getProof()
      .then(setProof)
      .catch(() => setProof(null));
    void loadSamples();
  }, [loadSamples]);

  const onRun = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const req = {
        mode,
        system_prompt: inputs.system_prompt,
        security_policy_yaml: inputs.security_policy_yaml,
        business_context: inputs.business_context,
        ...(mode === "agent_assisted" ? { provider_config: provider } : {}),
      };
      const res = await runAssessment(req);
      setResult(res);
      // Scroll to results on the next paint.
      requestAnimationFrame(() =>
        resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : "The assessment could not be completed. Please try again.";
      setError(msg);
    } finally {
      setRunning(false);
    }
  }, [mode, inputs, provider]);

  return (
    <AppShell proof={proof} online={online}>
      <div className="space-y-8">
        <Hero />
        <InputWorkspace
          value={inputs}
          onChange={setInputs}
          onLoadSamples={loadSamples}
          onReset={() => setInputs(EMPTY_INPUTS)}
          samplesLoading={samplesLoading}
        />
        <ModeProviderPanel
          mode={mode}
          onModeChange={setMode}
          provider={provider}
          onProviderChange={setProvider}
          onRun={onRun}
          running={running}
          error={error}
        />

        <div ref={resultsRef} className="space-y-8 scroll-mt-20">
          {result ? (
            <>
              <ReadinessSummary model={result.readiness} />
              <AuditTimeline steps={result.timeline} />
              <RedBlueDashboard model={result.red_blue} />
              <EvidenceReport model={result.evidence} />
              <OpenRisks model={result.evidence} />
              <EngineeringSafeguards items={result.safeguards} />
            </>
          ) : (
            <EmptyState />
          )}
        </div>
      </div>
    </AppShell>
  );
}
