// TypeScript contracts for the Noxus API. These mirror the pure-Python display
// models produced by `ui_formatters` and assembled in `api_core`. Honest labels
// ([DETERMINISTIC SIMULATION], [SEMANTIC LLM JUDGMENT], CONDITIONAL_PASS, open
// risks) are produced by the backend; the UI only renders them faithfully.

export type ChipColor = "green" | "amber" | "red" | "blue" | "neutral";

export type Mode = "deterministic" | "agent_assisted";

export type ProviderType =
  | "local_openai_compatible"
  | "openai_compatible"
  | "gemini_native";

export interface ProviderConfig {
  provider_type: ProviderType;
  base_url?: string;
  api_key?: string;
  red_model?: string;
  judge_model?: string;
  tuning_model?: string;
}

export interface SampleInputs {
  system_prompt: string;
  security_policy_yaml: string;
  business_context: string;
}

export interface HealthPayload {
  ok: boolean;
  product: string;
  mode: string;
}

export interface ProofIndicators {
  test_count: number | null;
  max_tuning_iterations: number;
  schema_bound_agents: boolean;
  deterministic_patch_engine: boolean;
  local_jsonl_audit_export: boolean;
}

export interface RunAssessmentRequest {
  mode: Mode;
  system_prompt: string;
  security_policy_yaml: string;
  business_context: string;
  provider_config?: ProviderConfig;
}

export interface ProbeSummary {
  total_probes: number;
  passed_probes: number;
  failed_probes: number;
  findings: number;
}

export interface ReadinessBadge {
  state: string;
  label: string;
  color: ChipColor;
  headline: string;
  explanation: string;
  is_pass: boolean;
}

export interface ReadinessSummary {
  badge: ReadinessBadge;
  before_score: number;
  after_score: number;
  score_delta: number;
  before_summary: ProbeSummary;
  after_summary: ProbeSummary;
  open_risk_count: number;
  human_review_count: number;
  proprietary_context_exposure_unresolved: boolean;
  proprietary_context_explanation: string;
  mode: string;
  tuning_iterations: number;
}

export interface TimelineStep {
  step: number;
  label: string;
  status: string;
  status_color: ChipColor;
  description: string;
  evidence_count: number;
  detail: string;
}

export interface FindingRow {
  finding_type: string;
  severity: string;
  severity_color: ChipColor;
  detection_mode: string;
  detection_label: string;
  detection_color: ChipColor;
  evidence: string;
  evidence_source: string;
  remediation_target: string[];
  remediation_target_label: string;
  confidence: string | null;
  probe_id: string;
  probe_type: string;
}

export interface ProbeRow {
  probe_id: string;
  probe_type: string;
  detection_mode: string;
  detection_label: string;
  detection_color: ChipColor;
  passed: boolean;
  status: string;
  status_color: ChipColor;
  num_findings: number;
  evidence: string[];
  findings: FindingRow[];
}

export interface PatchRow {
  operation: string;
  target: string;
  detail: string;
  source_finding: string | null;
  is_safety_rail: boolean;
}

export interface RedBlueModel {
  red: {
    title: string;
    baseline_probes: ProbeRow[];
    retest_probes: ProbeRow[];
    probes: ProbeRow[];
    findings: FindingRow[];
    failing_probes: ProbeRow[];
    before_summary: ProbeSummary;
    after_summary: ProbeSummary;
  };
  blue: {
    title: string;
    patches: PatchRow[];
    patch_engine_note: string;
    safety_rail_preview: string;
    human_review_requirements: string[];
    open_risks: string[];
  };
}

export interface EvidenceModel {
  readiness: ReadinessBadge;
  before_findings: FindingRow[];
  after_findings: FindingRow[];
  findings: FindingRow[];
  open_risks: string[];
  human_review_requirements: string[];
  proprietary_context_exposure_unresolved: boolean;
  proprietary_open_risks: string[];
  proprietary_context_explanation: string;
  before_score: number;
  after_score: number;
}

export interface SafeguardItem {
  title: string;
  detail: string;
  tone: ChipColor;
}

export type AgentRole = "red" | "judge" | "tuning";
export type StageStatus = "used" | "not_used" | "failed" | "human_review_required";

export interface AgentTraceStage {
  stage: string;
  role: AgentRole | null;
  model: string | null;
  provider_type: string | null;
  source: string;
  status: StageStatus;
  summary: string;
}

export interface AgentTrace {
  execution_mode: Mode;
  provider_type: string | null;
  red_model: string | null;
  judge_model: string | null;
  tuning_model: string | null;
  semantic_judgment_source: string;
  patch_proposal_source: string;
  stages: AgentTraceStage[];
}

export interface ProviderTestRoleResult {
  role: AgentRole;
  purpose: string;
  model: string;
  ok: boolean;
  latency_ms: number;
  response_validated: boolean;
  message: string;
}

export interface ProviderTestResponse {
  ok: boolean;
  provider_type: string;
  checked_at_utc: string;
  results: ProviderTestRoleResult[];
}

export interface AssessmentResponse {
  readiness: ReadinessSummary;
  timeline: TimelineStep[];
  red_blue: RedBlueModel;
  evidence: EvidenceModel;
  safeguards: SafeguardItem[];
  agent_trace: AgentTrace;
  execution_mode: string;
  provider_type: string | null;
  metadata: {
    mode: string;
    tuning_iterations: number;
    max_tuning_iterations: number;
  };
  report: unknown;
}

export interface ApiErrorBody {
  detail?: string;
}
