import pytest
from pydantic import ValidationError

from noxus.schemas import (
    DetectionMode,
    PatchOp,
    PatchOperation,
    PatchSet,
    Probe,
    ProbeResult,
    ProbeType,
    ReadinessReport,
    ReadinessState,
    ReportMetadata,
    SecurityPolicy,
    Severity,
    Finding,
)

VALID_POLICY = {
    "sensitive_data": {"block": ["api_key", "credit_card"], "mask": []},
    "prompt_injection": {"mode": "basic", "detect_indirect_instructions": False},
    "output_policy": {
        "block_confidential": True,
        "require_evidence_for_policy_claims": False,
    },
    "human_review": {"required_categories": []},
}


def test_policy_schema_accepts_valid_policy():
    policy = SecurityPolicy.model_validate(VALID_POLICY)
    assert policy.sensitive_data.block == ["api_key", "credit_card"]
    assert policy.prompt_injection.detect_indirect_instructions is False


def test_policy_schema_rejects_invalid_policy():
    bad = {"sensitive_data": {"block": "not-a-list"}, "unknown_field": 1}
    with pytest.raises(ValidationError):
        SecurityPolicy.model_validate(bad)


def test_probe_schema_accepts_valid_probe():
    probe = Probe(
        probe_id="p1",
        probe_type=ProbeType.indirect_prompt_injection,
        detection_mode=DetectionMode.deterministic_simulation,
        description="x",
    )
    assert probe.probe_type is ProbeType.indirect_prompt_injection


def test_patch_schema_accepts_allowed_operations():
    for op in PatchOp:
        operation = PatchOperation(operation=op, target="policy")
        assert operation.operation is op
    patch_set = PatchSet(
        operations=[
            PatchOperation(
                operation=PatchOp.insert_or_update_critical_safety_rail,
                target="system_prompt",
                clause_id="c1",
            )
        ]
    )
    assert patch_set.operations[0].clause_id == "c1"


def test_report_schema_exposes_detection_mode():
    finding = Finding(
        finding_type="indirect_prompt_injection_simulated",
        severity=Severity.high,
        detection_mode=DetectionMode.deterministic_simulation,
        probe_id="p1",
        probe_type=ProbeType.indirect_prompt_injection,
        description="d",
        evidence="e",
        evidence_source="deterministic_marker",
        remediation_target=["system_prompt", "security_policy"],
    )
    result = ProbeResult(
        probe_id="p1",
        probe_type=ProbeType.indirect_prompt_injection,
        detection_mode=DetectionMode.deterministic_simulation,
        passed=False,
        target_response="r",
        findings=[finding],
    )
    report = ReadinessReport(after_results=[result], readiness_state=ReadinessState.FAIL)
    assert report.after_results[0].detection_mode is DetectionMode.deterministic_simulation
    assert report.after_results[0].findings[0].detection_mode is DetectionMode.deterministic_simulation


def test_report_metadata_includes_business_context_documentation_only():
    meta = ReportMetadata(business_context_text="hello world")
    report = ReadinessReport(metadata=meta)
    assert report.metadata.business_context_text == "hello world"
    assert report.metadata.business_context_used_for == "documentation_only"
    assert report.metadata.milestone == "milestone_1_deterministic_skeleton"
