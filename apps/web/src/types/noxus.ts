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

export interface RemediationProgress {
  resolved: number;
  unresolved: number;
  label: string;
}

export interface ReadinessSummary {
  badge: ReadinessBadge;
  readiness_gate: string;
  before_score: number;
  after_score: number;
  after_score_label: string;
  after_score_explanation: string;
  remediation_progress: RemediationProgress;
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

export type PatchStatus =
  | "applied_and_resolved"
  | "applied_but_primary_unresolved"
  | "applied_but_related_risk_unresolved"
  | "applied_requires_human_review"
  | "rejected_unlinked";

export interface PatchRow {
  operation: string;
  target: string;
  detail: string;
  source_finding: string | null;
  source_finding_ids: string[];
  source_probe_ids: string[];
  source_finding_types: string[];
  // PRIMARY lineage is highlighted first; the rest is secondary/audit detail.
  primary_source_finding_type: string | null;
  primary_source_probe_id: string | null;
  primary_source_label: string;
  secondary_source_finding_ids: string[];
  source_label: string;
  status: PatchStatus;
  is_safety_rail: boolean;
}

export interface HumanReviewDerivationRow {
  category: string;
  derived_from_finding_types: string[];
  derived_from_probe_ids: string[];
  source: "derived_from_retest" | "proposed_by_agent";
  reason: string;
}

export interface RemediationModel {
  patch_application_count: number;
  patched_policy_effective: boolean;
  patched_system_prompt_effective: boolean;
  resolved_probe_count: number;
  unresolved_probe_count: number;
  resolved_finding_count: number;
  unresolved_finding_count: number;
  rejected_proposal_count: number;
  resolved_finding_types: string[];
  resolved_primary_finding_types: string[];
  unresolved_finding_types: string[];
  unresolved_findings: FindingRow[];
  human_review_categories: string[];
  human_review_derivation: HumanReviewDerivationRow[];
  remediation_progress: RemediationProgress;
  // Readiness GATE — reported separately from remediation progress.
  readiness_gate: string;
  readiness_gate_score: number;
  after_score: number;
  after_score_label: string;
  after_score_explanation: string;
  blocking_explanation: string;
}

export interface ReportSummary {
  readiness_gate: string;
  is_pass: boolean;
  what_improved: {
    resolved_finding_count: number;
    resolved_finding_types: string[];
    primary_finding_types_resolved: string[];
  };
  what_remains_blocked: {
    unresolved_finding_types: string[];
    human_review_categories: string[];
  };
  why_not_pass: string;
  summary_copy: string;
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
    rejected_proposals: PatchRow[];
    patch_engine_note: string;
    safety_rail_preview: string;
    human_review_requirements: string[];
    human_review_derivation: HumanReviewDerivationRow[];
    open_risks: string[];
    remediation: RemediationModel;
    resolved_finding_types: string[];
    unresolved_findings: FindingRow[];
    blocking_explanation: string;
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
export type StageStatus =
  | "used"
  | "not_used"
  | "failed"
  | "skipped"
  | "human_review_required";

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
  // Red-Team resilience trace (presentation-only). Non-null fallback_used means
  // the Red Team failed and the loop continued on deterministic baseline data.
  fallback_used: string | null;
  fallback_reason: string | null;
  continued_after_red_failure: boolean;
  baseline_probe_count: number;
  baseline_finding_count: number;
  // Which evidence base the before/after metrics were computed over, and the
  // semantic-judge resilience status (so a degraded run is never silent).
  evidence_basis: "deterministic_baseline" | "red_team_augmented" | "degraded_fallback" | null;
  semantic_judge_status: "used" | "failed" | "skipped" | null;
  // Timeout/fallback resilience trace (presentation-only).
  timeout_failed_role: string | null;
  timeout_fatal: boolean;
  tuning_fallback_used: boolean;
  tuning_fallback_model: string | null;
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
  debug_excerpt: string | null;
  // Distinguishes a TIMEOUT from a schema-contract failure (or none / ok).
  error_type: "timeout" | "schema" | "provider_error" | null;
  timed_out: boolean;
}

// Role-aware LLM timeout/provider-error diagnostics (presentation-only; no key).
export interface TimeoutFailure {
  failed_role: string;
  role_label: string;
  failed_stage: string | null;
  provider_type: string | null;
  model: string | null;
  timeout_seconds: number | null;
  retry_count: number;
  message: string | null;
  // True when the timeout routed the run to HUMAN_REVIEW_REQUIRED.
  fatal: boolean;
}

export interface TuningFallback {
  used: boolean;
  original_model: string | null;
  fallback_model: string | null;
  reason: string | null;
}

export interface SchemaFailure {
  failed_stage: string | null;
  failed_role: AgentRole | null;
  debug_excerpt: string | null;
  baseline_preserved: boolean;
  baseline_probe_count: number;
  baseline_finding_count: number;
  reason: string;
}

// Red Team failure diagnostics. Present whenever the Red Team Agent failed its
// schema contract — both for a degraded-but-continued run (fallback to the
// deterministic baseline) and for an abort. Honest, never hidden.
export interface RedTeamFailure {
  failed: boolean;
  failed_stage: string;
  failed_role: AgentRole;
  source: string;
  fallback_used: string | null;
  fallback_reason: string | null;
  continued_after_red_failure: boolean;
  baseline_preserved: boolean;
  baseline_probe_count: number;
  baseline_finding_count: number;
  debug_excerpt: string | null;
}

// Semantic Judge failure diagnostics. Present when the judge broke its schema
// contract but the loop DEGRADED and continued on deterministic + valid
// red-team evidence (no semantic findings fabricated). Symmetric with
// RedTeamFailure.
export interface SemanticJudgeFailure {
  failed: boolean;
  failed_stage: string;
  failed_role: AgentRole;
  source: string;
  fallback_basis: string | null;
  continued: boolean;
  baseline_preserved: boolean;
  baseline_probe_count: number;
  baseline_finding_count: number;
  debug_excerpt: string | null;
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
  remediation: RemediationModel;
  report_summary: ReportSummary;
  evidence: EvidenceModel;
  safeguards: SafeguardItem[];
  agent_trace: AgentTrace;
  execution_mode: string;
  provider_type: string | null;
  schema_failure: SchemaFailure | null;
  red_team_failure: RedTeamFailure | null;
  semantic_judge_failure: SemanticJudgeFailure | null;
  timeout_failure: TimeoutFailure | null;
  tuning_fallback: TuningFallback | null;
  metadata: {
    mode: string;
    tuning_iterations: number;
    max_tuning_iterations: number;
    evidence_basis: "deterministic_baseline" | "red_team_augmented" | "degraded_fallback" | null;
  };
  report: unknown;
}

export interface ApiErrorBody {
  detail?: string;
}

export interface PolicyErrorDetail {
  message: string;
  code: "policy_schema" | "policy_yaml";
  unsupported_keys?: string[];
  allowed_keys?: string[];
  example_yaml?: string;
}
