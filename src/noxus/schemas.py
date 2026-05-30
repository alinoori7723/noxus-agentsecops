"""Strict Pydantic v2 schemas for the Noxus AgentSecOps Milestone 1 skeleton.

Everything here is deterministic data: policies, probes, findings, patches and
reports. No runtime behavior, no LLM, no network.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class ProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_id: str
    probe_type: ProbeType
    detection_mode: DetectionMode
    passed: bool
    target_response: str
    findings: list[Finding] = Field(default_factory=list)


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


class ReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probes_run: list[str] = Field(default_factory=list)
    before_results: list[ProbeResult] = Field(default_factory=list)
    after_results: list[ProbeResult] = Field(default_factory=list)
    patch_operations_applied: list[PatchOperation] = Field(default_factory=list)
    before_score: int = 0
    after_score: int = 0
    readiness_state: ReadinessState = ReadinessState.FAIL
    open_risks: list[str] = Field(default_factory=list)
    human_review_requirements: list[str] = Field(default_factory=list)
    metadata: ReportMetadata = Field(default_factory=ReportMetadata)
