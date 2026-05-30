from noxus.patch_mapper import generate_patches_from_findings
from noxus.schemas import (
    DetectionMode,
    Finding,
    PatchOp,
    PatchSet,
    ProbeType,
    Severity,
)


def _finding(finding_type, ptype, mode=DetectionMode.deterministic):
    return Finding(
        finding_type=finding_type,
        severity=Severity.high,
        detection_mode=mode,
        probe_id="p",
        probe_type=ptype,
        description="d",
        evidence="e",
        evidence_source="src",
        remediation_target=["security_policy"],
    )


def test_generate_patches_from_indirect_injection_finding():
    finding = _finding(
        "indirect_prompt_injection_simulated",
        ProbeType.indirect_prompt_injection,
        DetectionMode.deterministic_simulation,
    )
    patch_set = generate_patches_from_findings([finding])
    ops = {op.operation for op in patch_set.operations}
    assert PatchOp.insert_or_update_critical_safety_rail in ops
    assert PatchOp.set_control_level in ops
    assert PatchOp.require_human_review_for_category in ops
    # The safety rail must carry a stable clause_id.
    rail = next(
        op
        for op in patch_set.operations
        if op.operation is PatchOp.insert_or_update_critical_safety_rail
    )
    assert rail.clause_id
    assert rail.target == "system_prompt"


def test_generate_patches_from_findings_does_not_emit_unrelated_patches():
    finding = _finding(
        "indirect_prompt_injection_simulated",
        ProbeType.indirect_prompt_injection,
        DetectionMode.deterministic_simulation,
    )
    patch_set = generate_patches_from_findings([finding])
    # No PII/secret masking patches should appear for an indirect-only finding.
    mask_types = {op.mask_type for op in patch_set.operations if op.mask_type}
    block_types = {op.block_type for op in patch_set.operations if op.block_type}
    assert "email" not in mask_types
    assert "phone" not in mask_types
    assert "customer_id" not in mask_types
    assert "api_key" not in block_types


def test_generate_patches_returns_schema_valid_patchset():
    findings = [
        _finding("customer_identifier_leakage", ProbeType.customer_identifier_leakage),
        _finding("pii_leakage", ProbeType.pii_leakage),
        _finding("fake_secret_exfiltration", ProbeType.fake_secret_exfiltration),
    ]
    patch_set = generate_patches_from_findings(findings)
    # Round-trips through schema validation without error.
    assert isinstance(PatchSet.model_validate(patch_set.model_dump()), PatchSet)
    mask_types = {op.mask_type for op in patch_set.operations if op.mask_type}
    assert {"customer_id", "internal_ticket_id", "email", "phone"} <= mask_types
