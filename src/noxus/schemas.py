"""Strict Pydantic v2 schemas for the Noxus AgentSecOps Milestone 1 skeleton.

Everything here is deterministic data: policies, probes, findings, patches and
reports. No runtime behavior, no LLM, no network.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------------------------------- #
# Enums / controlled vocabularies
# --------------------------------------------------------------------------- #
class ProbeType(str, Enum):
    indirect_prompt_injection = "indirect_prompt_injection"
    pii_leakage = "pii_leakage"
    fake_secret_exfiltration = "fake_secret_exfiltration"
    customer_identifier_leakage = "customer_identifier_leakage"
    proprietary_context_exposure = "proprietary_context_exposure"
    policy_conflict_probe = "policy_conflict_probe"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class DetectionMode(str, Enum):
    deterministic = "deterministic"
    deterministic_simulation = "deterministic_simulation"
    # NOTE: semantic_llm exists for forward compatibility only. Milestone 1 must
    # never use it during actual execution.
    semantic_llm = "semantic_llm"


class ReadinessState(str, Enum):
    PASS = "PASS"
    CONDITIONAL_PASS = "CONDITIONAL_PASS"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    FAIL = "FAIL"


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class PatchOp(str, Enum):
    add_control = "add_control"
    add_mask_type = "add_mask_type"
    add_block_type = "add_block_type"
    set_control_level = "set_control_level"
    insert_or_update_critical_safety_rail = "insert_or_update_critical_safety_rail"
    add_output_constraint = "add_output_constraint"
    require_human_review_for_category = "require_human_review_for_category"


# --------------------------------------------------------------------------- #
# Security policy
# --------------------------------------------------------------------------- #
class SensitiveData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block: list[str] = Field(default_factory=list)
    mask: list[str] = Field(default_factory=list)


class PromptInjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = "basic"
    detect_indirect_instructions: bool = False


class OutputPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_confidential: bool = True
    require_evidence_for_policy_claims: bool = False


class HumanReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_categories: list[str] = Field(default_factory=list)


class SecurityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensitive_data: SensitiveData = Field(default_factory=SensitiveData)
    prompt_injection: PromptInjection = Field(default_factory=PromptInjection)
    output_policy: OutputPolicy = Field(default_factory=OutputPolicy)
    human_review: HumanReview = Field(default_factory=HumanReview)


# --------------------------------------------------------------------------- #
# Probes
# --------------------------------------------------------------------------- #
class Probe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_id: str
    probe_type: ProbeType
    detection_mode: DetectionMode
    description: str
    # Substrings that must never appear in the target output for this probe.
    must_not_appear_in_output: list[str] = Field(default_factory=list)
    # Documentation of the deterministic failure markers expected before patching
    # (used by the indirect_prompt_injection simulation).
    expected_failure_markers: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Findings / probe results
# --------------------------------------------------------------------------- #
class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_type: str
    severity: Severity
    detection_mode: DetectionMode
    probe_id: str
    probe_type: ProbeType
    description: str
    evidence: str
    evidence_source: str
    remediation_target: list[str] = Field(default_factory=list)
    # Milestone 3 (display telemetry only): present for semantic-judge findings so
    # the UI can show the judge's confidence. Defaults to None for deterministic
    # findings; does not affect evaluator/agent/patch behavior or scoring.
    confidence: Optional[Confidence] = None


class ProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_id: str
    probe_type: ProbeType
    detection_mode: DetectionMode
    passed: bool
    target_response: str
    findings: list[Finding] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Milestone 2 — agent layer schemas (schema-bound LLM outputs)
# --------------------------------------------------------------------------- #
class ProbeBatch(BaseModel):
    """A schema-bound batch of probes proposed by the Red Team Agent."""

    model_config = ConfigDict(extra="forbid")

    probes: list[Probe] = Field(default_factory=list)


class SemanticJudgment(BaseModel):
    """A schema-bound judgment produced by the LLM semantic judge.

    The semantic judge supplements (never replaces) the deterministic
    evaluator. Its detection_mode is always semantic_llm.
    """

    model_config = ConfigDict(extra="forbid")

    probe_id: str
    semantic_violation: bool
    confidence: Confidence
    reason: str
    suggested_finding_type: str
    detection_mode: DetectionMode = DetectionMode.semantic_llm

    @field_validator("detection_mode")
    @classmethod
    def _must_be_semantic(cls, value: DetectionMode) -> DetectionMode:
        if value is not DetectionMode.semantic_llm:
            raise ValueError(
                "SemanticJudgment.detection_mode must be 'semantic_llm'."
            )
        return value


# --------------------------------------------------------------------------- #
# Patches
# --------------------------------------------------------------------------- #
class PatchOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: PatchOp
    target: str  # "system_prompt" or "policy"
    # Safety-rail fields
    clause_id: Optional[str] = None
    heading: Optional[str] = None
    content: Optional[str] = None
    # Generic policy-set fields
    path: Optional[str] = None
    value: Optional[Any] = None
    # Sensitive-data fields
    mask_type: Optional[str] = None
    block_type: Optional[str] = None
    # Control / constraint / human-review fields
    control: Optional[str] = None
    constraint: Optional[str] = None
    category: Optional[str] = None
    # Traceability back to the finding that motivated this patch.
    source_finding: Optional[str] = None
    # Evidence lineage (backward-compatible; default empty). Populated
    # deterministically by ``remediation.attach_patch_lineage`` so every applied
    # patch cites the finding(s)/probe(s) it addresses (no "not specified").
    source_finding_ids: list[str] = Field(default_factory=list)
    source_probe_ids: list[str] = Field(default_factory=list)
    source_finding_types: list[str] = Field(default_factory=list)
    # PRIMARY lineage: the single finding type/probe this operation is principally
    # meant to remediate. Patch status is computed from the PRIMARY target so a
    # prompt-injection patch is not marked "unresolved" merely because an
    # unrelated finding co-occurred. The remaining links are secondary/audit.
    primary_source_finding_type: Optional[str] = None
    primary_source_probe_id: Optional[str] = None
    secondary_source_finding_ids: list[str] = Field(default_factory=list)


class PatchSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[PatchOperation] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
class ReportMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_context_text: str = ""
    business_context_used_for: str = "documentation_only"
    milestone: str = "milestone_1_deterministic_skeleton"
    # Milestone 2: which orchestration mode produced this report, and how many
    # bounded tuning iterations ran (0 in pure deterministic mode).
    mode: str = "deterministic"
    tuning_iterations: int = 0
    # Presentation-only telemetry for an agent-assisted schema-contract failure.
    # These never affect scoring/readiness; they let the UI render a partial
    # failure (which agent stage failed) with a sanitized excerpt of the output.
    failed_stage: Optional[str] = None
    failed_role: Optional[str] = None
    schema_failure_excerpt: Optional[str] = None
    # Presentation-only Red-Team resilience telemetry. When the Red Team Agent
    # fails schema validation but the deterministic baseline already produced
    # findings, the loop DEGRADES rather than aborting: it continues using the
    # deterministic baseline probes/findings as the fallback evidence source.
    # These fields record that honestly (they never fabricate a Red Team success
    # and never affect scoring/readiness):
    #   red_team_status            "used" | "failed" | None (deterministic mode)
    #   fallback_used              "deterministic_baseline" | None
    #   fallback_reason            "red_team_schema_contract_failure" | None
    #   continued_after_red_failure  True only when the loop continued past a
    #                                Red Team failure on baseline evidence
    #   red_team_failure_excerpt   sanitized (<=500 chars, secrets redacted)
    red_team_status: Optional[str] = None
    fallback_used: Optional[str] = None
    fallback_reason: Optional[str] = None
    continued_after_red_failure: bool = False
    red_team_failure_excerpt: Optional[str] = None
    # Presentation-only Semantic-Judge resilience telemetry (symmetric with the
    # Red-Team fields above). The judge SUPPLEMENTS deterministic findings; if it
    # breaks its schema contract the loop DEGRADES — it drops the (unusable)
    # semantic supplement, keeps the deterministic + valid red-team evidence, and
    # continues to policy tuning. It never fabricates semantic findings.
    #   semantic_judge_status         "used" | "failed" | "skipped" | None
    #   semantic_judge_failure_excerpt sanitized (<=500 chars, secrets redacted)
    semantic_judge_status: Optional[str] = None
    semantic_judge_failure_excerpt: Optional[str] = None
    # Presentation-only label for WHICH evidence base the before/after metrics were
    # computed over, so a degraded run never silently compares different bases:
    #   "deterministic_baseline"  pure deterministic mode
    #   "red_team_augmented"      agent mode, Red Team succeeded (baseline + probes)
    #   "degraded_fallback"       agent mode, Red Team failed -> deterministic baseline
    evidence_basis: Optional[str] = None
    # Remediation-effectiveness telemetry (presentation/audit only; never affects
    # scoring/readiness). Lets the UI distinguish "patch applied" from "risk
    # fixed", and verifies the retest ran against the patched target.
    patched_policy_effective: bool = False
    patched_system_prompt_effective: bool = False
    patch_application_count: int = 0
    resolved_probe_count: int = 0
    unresolved_probe_count: int = 0
    resolved_finding_count: int = 0
    unresolved_finding_count: int = 0
    # Count of LLM-proposed patch operations rejected for missing evidence lineage
    # (never applied, never counted as remediation).
    rejected_proposal_count: int = 0
    # Presentation-only LLM TIMEOUT diagnostics (never affect scoring/readiness).
    # Set whenever a role's provider call timed out (fatally -> HUMAN_REVIEW, or
    # non-fatally e.g. a degraded judge). All values are safe to surface: no API
    # key, no request body. ``timeout_message`` is secret-redacted.
    timeout_failed_role: Optional[str] = None
    timeout_failed_stage: Optional[str] = None
    timeout_provider_type: Optional[str] = None
    timeout_model: Optional[str] = None
    timeout_seconds: Optional[float] = None
    timeout_retry_count: int = 0
    timeout_message: Optional[str] = None
    # True when the timeout caused the run to route to HUMAN_REVIEW_REQUIRED
    # (vs a non-fatal degrade such as a judge supplement timing out).
    timeout_fatal: bool = False
    # Optional Policy-Tuning fallback-model telemetry (Fix 4). Recorded honestly
    # so a fallback is NEVER silently hidden; the original timeout stays visible.
    tuning_fallback_used: bool = False
    tuning_fallback_original_model: Optional[str] = None
    tuning_fallback_model: Optional[str] = None
    tuning_fallback_reason: Optional[str] = None


class ReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probes_run: list[str] = Field(default_factory=list)
    before_results: list[ProbeResult] = Field(default_factory=list)
    after_results: list[ProbeResult] = Field(default_factory=list)
    patch_operations_applied: list[PatchOperation] = Field(default_factory=list)
    # LLM-proposed operations rejected for missing evidence lineage. Recorded for
    # an honest audit trail; NEVER applied and NEVER counted as remediation.
    rejected_patch_operations: list[PatchOperation] = Field(default_factory=list)
    before_score: int = 0
    after_score: int = 0
    readiness_state: ReadinessState = ReadinessState.FAIL
    open_risks: list[str] = Field(default_factory=list)
    human_review_requirements: list[str] = Field(default_factory=list)
    metadata: ReportMetadata = Field(default_factory=ReportMetadata)
    # Milestone 3 (presentation telemetry only, backward-compatible): the real
    # patched system prompt produced by the deterministic patch engine during
    # the run. Used by the UI to render an HONEST safety-rail preview. Defaults
    # to None; does not affect scoring, readiness, evaluator, agent, or patch
    # behavior.
    after_system_prompt: Optional[str] = None
