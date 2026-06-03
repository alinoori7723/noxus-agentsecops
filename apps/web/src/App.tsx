import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { TopHeader } from "./components/TopHeader";
import { NAV_ITEMS, type SectionId } from "./components/nav";
import { Overview } from "./components/Overview";
import { InputWorkspace, type TargetInputs } from "./components/InputWorkspace";
import { AssessmentPanel } from "./components/AssessmentPanel";
import {
  ProviderSettings,
  type ProviderTestState,
  baseUrlError,
} from "./components/ProviderSettings";
import { EmptyState } from "./components/EmptyState";
import { ReadinessSummary } from "./components/ReadinessSummary";
import { RoleObservability } from "./components/RoleObservability";
import { AuditTimeline } from "./components/AuditTimeline";
import { RedBlueDashboard } from "./components/RedBlueDashboard";
import { EvidenceReport } from "./components/EvidenceReport";
import { OpenRisks } from "./components/OpenRisks";
import { EngineeringSafeguards } from "./components/EngineeringSafeguards";
import { PolicyError } from "./components/PolicyError";
import { PartialRunBanner } from "./components/PartialRunBanner";
import {
  getHealth,
  getProof,
  getSampleInputs,
  runAssessment,
  testProvider,
  ApiError,
} from "./api/client";
import type {
  AgentRole,
  AssessmentResponse,
  Mode,
  PolicyErrorDetail,
  ProofIndicators,
  ProviderConfig,
} from "./types/noxus";

function isPolicySchemaError(data: unknown): data is PolicyErrorDetail {
  return (
    typeof data === "object" &&
    data !== null &&
    "code" in data &&
    ((data as { code?: string }).code === "policy_schema" ||
      (data as { code?: string }).code === "policy_yaml")
  );
}

function providerSignature(p: ProviderConfig): string {
  return JSON.stringify([
    p.provider_type,
    p.base_url ?? "",
    p.api_key ?? "",
    p.red_model ?? "",
    p.judge_model ?? "",
    p.tuning_model ?? "",
  ]);
}

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
  const [section, setSection] = useState<SectionId>("overview");
  const [inputs, setInputs] = useState<TargetInputs>(EMPTY_INPUTS);
  const [sampleInputs, setSampleInputs] = useState<TargetInputs>(EMPTY_INPUTS);
  const [loadedFromSample, setLoadedFromSample] = useState(false);
  const [mode, setMode] = useState<Mode>("deterministic");
  const [provider, setProvider] = useState<ProviderConfig>(DEFAULT_PROVIDER);

  const [proof, setProof] = useState<ProofIndicators | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [samplesLoading, setSamplesLoading] = useState(false);

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [policyError, setPolicyError] = useState<PolicyErrorDetail | null>(null);
  const [result, setResult] = useState<AssessmentResponse | null>(null);

  const [providerTest, setProviderTest] = useState<{
    status: ProviderTestState["status"];
    response: ProviderTestState["response"];
    error: string | null;
    testedSignature: string | null;
  }>({ status: "idle", response: null, error: null, testedSignature: null });

  const onTestProvider = useCallback(
    async (roles: AgentRole[]) => {
      const urlErr = baseUrlError(provider);
      if (urlErr) {
        setProviderTest({
          status: "done",
          response: null,
          error: urlErr,
          testedSignature: null,
        });
        return;
      }
      setProviderTest((s) => ({ ...s, status: "testing", error: null }));
      try {
        const response = await testProvider(provider, roles);
        setProviderTest({
          status: "done",
          response,
          error: null,
          testedSignature: providerSignature(provider),
        });
      } catch (e) {
        const msg =
          e instanceof ApiError ? e.message : "Provider test could not be completed.";
        setProviderTest({
          status: "done",
          response: null,
          error: msg,
          testedSignature: null,
        });
      }
    },
    [provider],
  );

  const providerStale =
    providerTest.testedSignature !== null &&
    providerTest.testedSignature !== providerSignature(provider);
  const providerTestOk = providerTest.response?.ok === true;

  const loadSamples = useCallback(async () => {
    setSamplesLoading(true);
    try {
      const s = await getSampleInputs();
      const next = {
        system_prompt: s.system_prompt,
        security_policy_yaml: s.security_policy_yaml,
        business_context: s.business_context,
      };
      setSampleInputs(next);
      setInputs(next);
      setLoadedFromSample(true);
    } catch {
      // leave inputs unchanged on failure
    } finally {
      setSamplesLoading(false);
    }
  }, []);

  useEffect(() => {
    getHealth()
      .then((h) => setOnline(Boolean(h.ok)))
      .catch(() => setOnline(false));
    getProof()
      .then(setProof)
      .catch(() => setProof(null));
    void loadSamples();
  }, [loadSamples]);

  const run = useCallback(
    async (runMode: Mode) => {
      // Client-side guard: never send an invalid base URL to the backend.
      if (runMode === "agent_assisted") {
        const urlErr = baseUrlError(provider);
        if (urlErr) {
          setPolicyError(null);
          setError(urlErr);
          setSection("provider");
          return;
        }
      }
      setRunning(true);
      setError(null);
      setPolicyError(null);
      try {
        const req = {
          mode: runMode,
          system_prompt: inputs.system_prompt,
          security_policy_yaml: inputs.security_policy_yaml,
          business_context: inputs.business_context,
          ...(runMode === "agent_assisted" ? { provider_config: provider } : {}),
        };
        const res = await runAssessment(req);
        setResult(res);
        setSection("results");
      } catch (e) {
        if (e instanceof ApiError && isPolicySchemaError(e.data)) {
          setPolicyError(e.data as PolicyErrorDetail);
          setSection("target");
        } else {
          const msg =
            e instanceof ApiError
              ? e.message
              : "The assessment could not be completed. Please try again.";
          setError(msg);
        }
      } finally {
        setRunning(false);
      }
    },
    [inputs, provider],
  );

  const resetTab = useCallback(
    (key: keyof TargetInputs) =>
      setInputs((prev) => ({ ...prev, [key]: sampleInputs[key] })),
    [sampleInputs],
  );

  const resetPolicyToSample = useCallback(() => {
    setInputs((prev) => ({
      ...prev,
      security_policy_yaml: sampleInputs.security_policy_yaml,
    }));
    setPolicyError(null);
  }, [sampleInputs]);

  const navItem = NAV_ITEMS.find((n) => n.id === section)!;

  return (
    <div className="flex h-full min-h-screen bg-canvas">
      <Sidebar active={section} onSelect={setSection} hasResult={result !== null} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopHeader
          title={navItem.label === "Overview" ? "Noxus AgentSecOps" : navItem.label}
          subtitle={navItem.subtitle}
          proof={proof}
          online={online}
        />
        <main className="mx-auto w-full max-w-[1200px] flex-1 px-6 py-7 lg:px-8">
          {section === "overview" && (
            <Overview
              onConfigure={() => setSection("target")}
              onRunDemo={() => {
                setMode("deterministic");
                void run("deterministic");
              }}
              running={running}
            />
          )}

          {section === "target" && (
            <div className="space-y-4">
              {policyError && (
                <PolicyError
                  detail={policyError}
                  onResetPolicy={resetPolicyToSample}
                />
              )}
              <InputWorkspace
                value={inputs}
                onChange={setInputs}
                onLoadSamples={loadSamples}
                onResetTab={resetTab}
                samplesLoading={samplesLoading}
                loadedFromSample={loadedFromSample}
              />
            </div>
          )}

          {section === "assessment" && (
            <AssessmentPanel
              mode={mode}
              onModeChange={setMode}
              provider={provider}
              onGoToProvider={() => setSection("provider")}
              onRun={() => void run(mode)}
              running={running}
              error={error}
              providerTestOk={providerTestOk}
              providerTestStale={providerStale}
              providerConfigError={baseUrlError(provider)}
            />
          )}

          {section === "provider" && (
            <ProviderSettings
              provider={provider}
              onChange={setProvider}
              testState={{
                status: providerTest.status,
                response: providerTest.response,
                error: providerTest.error,
                stale: providerStale,
              }}
              onTest={onTestProvider}
            />
          )}

          {section === "results" &&
            (result ? (
              <div className="space-y-6">
                {result.schema_failure && (
                  <PartialRunBanner failure={result.schema_failure} />
                )}
                <ReadinessSummary model={result.readiness} />
                <RoleObservability
                  trace={result.agent_trace}
                  evidence={result.evidence}
                />
                <AuditTimeline steps={result.timeline} />
                <RedBlueDashboard model={result.red_blue} />
              </div>
            ) : (
              <EmptyState onGoToAssessment={() => setSection("assessment")} />
            ))}

          {section === "evidence" &&
            (result ? (
              <EvidenceReport model={result.evidence} />
            ) : (
              <EmptyState onGoToAssessment={() => setSection("assessment")} />
            ))}

          {section === "risks" &&
            (result ? (
              <OpenRisks model={result.evidence} />
            ) : (
              <EmptyState onGoToAssessment={() => setSection("assessment")} />
            ))}

          {section === "proof" && (
            <EngineeringSafeguards items={result?.safeguards ?? []} />
          )}
        </main>
      </div>
    </div>
  );
}
