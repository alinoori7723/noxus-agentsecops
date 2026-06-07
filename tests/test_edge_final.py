"""Final edge-case QA: multi-instance unresolved routing + security-aware
primary-lineage tie-breaker (browser-free, deterministic)."""

from noxus import remediation, ui_formatters
from noxus.schemas import (
    DetectionMode,
    Finding,
    PatchOp,
    PatchOperation,
    ProbeResult,
    ProbeType,
    ReadinessReport,
    ReadinessState,
    ReportMetadata,
    Severity,
)


def _mk_finding(finding_type, probe_type, severity=Severity.high, probe_id="p"):
    return Finding(
        finding_type=finding_type, severity=severity,
        detection_mode=DetectionMode.deterministic, probe_id=probe_id,
        probe_type=probe_type, description="d", evidence="e", evidence_source="s",
    )


def _mk_result(probe_id, probe_type, findings):
    return ProbeResult(
        probe_id=probe_id, probe_type=probe_type,
        detection_mode=DetectionMode.deterministic,
        passed=len(findings) == 0, target_response="r", findings=findings,
    )


def _report(*, before, after, after_score=0, before_score=100,
            state=ReadinessState.HUMAN_REVIEW_REQUIRED, human_review=(), meta=None):
    return ReadinessReport(
        before_results=list(before), after_results=list(after),
        before_score=before_score, after_score=after_score, readiness_state=state,
        human_review_requirements=list(human_review),
        metadata=meta or ReportMetadata(),
    )


# --------------------------------------------------------------------------- #
# Fix 1 — multi-instance unresolved routing (multiple types, multiple instances)
# --------------------------------------------------------------------------- #
def _multi_unresolved_report():
    """4 unresolved instances across 4 types: 3 high-risk -> human review, 1
    low/unmapped -> explicit non-review bucket."""
    after = [
        _mk_result("p_pii", ProbeType.pii_leakage,
                   [_mk_finding("pii_leakage", ProbeType.pii_leakage,
                                Severity.high, "p_pii")]),
        _mk_result("p_sec", ProbeType.fake_secret_exfiltration,
                   [_mk_finding("fake_secret_exfiltration",
                                ProbeType.fake_secret_exfiltration,
                                Severity.high, "p_sec")]),
        _mk_result("p_cust", ProbeType.customer_identifier_leakage,
                   [_mk_finding("customer_identifier_leakage",
                                ProbeType.customer_identifier_leakage,
                                Severity.high, "p_cust")]),
        # Low-severity, unmapped finding -> no human-review category.
        _mk_result("p_misc", ProbeType.policy_conflict_probe,
                   [_mk_finding("policy_conflict_note",
                                ProbeType.policy_conflict_probe,
                                Severity.low, "p_misc")]),
    ]
    meta = ReportMetadata(resolved_finding_count=0, unresolved_finding_count=4)
    return _report(before=after, after=after, after_score=0,
                   state=ReadinessState.HUMAN_REVIEW_REQUIRED,
                   human_review=["pii", "secrets", "customer_identifier"], meta=meta)


def test_multi_unresolved_findings_all_instances_accounted_for():
    model = ui_formatters.build_remediation_model(_multi_unresolved_report())
    instances = model["unresolved_finding_instances"]
    assert len(instances) == 4
    types = {i["finding_type"] for i in instances}
    assert len(types) >= 3
    routed = model["human_review_derived_finding_instance_count"]
    not_reviewed = len(model["unresolved_not_human_reviewed"])
    assert routed + not_reviewed == len(instances)


def test_multi_unresolved_high_risk_findings_route_to_human_review():
    model = ui_formatters.build_remediation_model(_multi_unresolved_report())
    routed_ids = {
        fid for row in model["human_review_derivation"]
        for fid in row["derived_from_finding_instance_ids"]
    }
    assert len(routed_ids) >= 3  # pii, secrets, customer_identifier instances


def test_non_reviewed_unresolved_findings_have_explicit_reason():
    model = ui_formatters.build_remediation_model(_multi_unresolved_report())
    not_reviewed = model["unresolved_not_human_reviewed"]
    assert len(not_reviewed) == 1
    # The single non-reviewed instance is the low-severity / unmapped one.
    assert not_reviewed[0]["finding_type"] == "policy_conflict_note"
    assert not_reviewed[0]["severity"] == "low"
    assert not_reviewed[0]["reason"]


def test_human_review_instance_count_matches_multi_instance_routing():
    model = ui_formatters.build_remediation_model(_multi_unresolved_report())
    routed = sum(
        len(row["derived_from_finding_instance_ids"])
        for row in model["human_review_derivation"]
    )
    assert model["human_review_derived_finding_instance_count"] == routed == 3


def test_human_review_type_count_matches_unique_routed_types():
    model = ui_formatters.build_remediation_model(_multi_unresolved_report())
    routed_types = {
        t for row in model["human_review_derivation"]
        for t in row["derived_from_finding_types"]
    }
    assert model["human_review_derived_finding_type_count"] == len(routed_types) == 3
    assert routed_types == {
        "pii_leakage", "fake_secret_exfiltration", "customer_identifier_leakage",
    }


def test_no_unresolved_instance_disappears_in_multi_type_case():
    model = ui_formatters.build_remediation_model(_multi_unresolved_report())
    all_ids = [i["instance_id"] for i in model["unresolved_finding_instances"]]
    assert len(set(all_ids)) == len(all_ids) == 4
    accounted = {
        fid for row in model["human_review_derivation"]
        for fid in row["derived_from_finding_instance_ids"]
    } | {i["instance_id"] for i in model["unresolved_not_human_reviewed"]}
    assert accounted == set(all_ids)


# --------------------------------------------------------------------------- #
# Fix 3 — security-aware primary-lineage tie-breaker
# --------------------------------------------------------------------------- #
def test_primary_lineage_prefers_domain_specific_over_sorted_id():
    # must_not_appear_violation sorts before pii_leakage, but the PII patch domain
    # wins -> pii_leakage is primary, not the alphabetically-first generic finding.
    findings = [
        _mk_finding("must_not_appear_violation",
                    ProbeType.proprietary_context_exposure, Severity.high, "a_prop"),
        _mk_finding("pii_leakage", ProbeType.pii_leakage, Severity.high, "z_pii"),
    ]
    op = PatchOperation(operation=PatchOp.add_mask_type, target="policy",
                        mask_type="pii",
                        source_probe_ids=["a_prop", "z_pii"])
    linked, _ = remediation.attach_patch_lineage([op], findings)
    assert linked[0].primary_source_finding_type == "pii_leakage"


def test_primary_lineage_prefers_same_cited_probe_within_domain():
    # Two equal-severity pii findings; the cited probe wins even though the other
    # probe id sorts first.
    findings = [
        _mk_finding("pii_leakage", ProbeType.pii_leakage, Severity.high, "probe_a"),
        _mk_finding("pii_leakage", ProbeType.pii_leakage, Severity.high, "probe_x"),
    ]
    op = PatchOperation(operation=PatchOp.add_mask_type, target="policy",
                        mask_type="pii", source_probe_ids=["probe_x"])
    linked, _ = remediation.attach_patch_lineage([op], findings)
    assert linked[0].primary_source_probe_id == "probe_x"


def test_primary_lineage_prefers_higher_severity_within_domain():
    # No cited probe; the higher-severity finding wins over the sorted-first one.
    findings = [
        _mk_finding("pii_leakage", ProbeType.pii_leakage, Severity.medium, "probe_a"),
        _mk_finding("pii_leakage", ProbeType.pii_leakage, Severity.critical, "probe_z"),
    ]
    op = PatchOperation(operation=PatchOp.add_mask_type, target="policy",
                        mask_type="pii")
    linked, _ = remediation.attach_patch_lineage([op], findings)
    assert linked[0].primary_source_probe_id == "probe_z"


def test_sorted_id_used_only_as_final_tie_breaker():
    # Same domain, no cited probe, equal severity -> sorted probe id decides.
    findings = [
        _mk_finding("pii_leakage", ProbeType.pii_leakage, Severity.high, "probe_b"),
        _mk_finding("pii_leakage", ProbeType.pii_leakage, Severity.high, "probe_a"),
    ]
    op = PatchOperation(operation=PatchOp.add_mask_type, target="policy",
                        mask_type="pii")
    linked, _ = remediation.attach_patch_lineage([op], findings)
    assert linked[0].primary_source_probe_id == "probe_a"


def test_must_not_appear_never_beats_specific_pii_secret_customer_prompt():
    mna = _mk_finding("must_not_appear_violation",
                      ProbeType.proprietary_context_exposure, Severity.critical,
                      "a_prop")
    cases = [
        (PatchOp.add_mask_type, {"mask_type": "pii"},
         _mk_finding("pii_leakage", ProbeType.pii_leakage, Severity.low, "z_pii"),
         "pii_leakage"),
        (PatchOp.add_block_type, {"block_type": "secrets"},
         _mk_finding("fake_secret_exfiltration",
                     ProbeType.fake_secret_exfiltration, Severity.low, "z_sec"),
         "fake_secret_exfiltration"),
        (PatchOp.add_mask_type, {"mask_type": "customer_id"},
         _mk_finding("customer_identifier_leakage",
                     ProbeType.customer_identifier_leakage, Severity.low, "z_cust"),
         "customer_identifier_leakage"),
        (PatchOp.set_control_level,
         {"path": "prompt_injection.detect_indirect_instructions", "value": True},
         _mk_finding("indirect_prompt_injection_simulated",
                     ProbeType.indirect_prompt_injection, Severity.low, "z_inj"),
         "indirect_prompt_injection_simulated"),
    ]
    for operation, fields, specific, expected in cases:
        # The generic must_not_appear is critical-severity and sorts first, yet the
        # specific (even low-severity) finding must remain primary for its domain.
        op = PatchOperation(operation=operation, target="policy",
                            source_probe_ids=["a_prop", specific.probe_id], **fields)
        linked, _ = remediation.attach_patch_lineage([op], [mna, specific])
        assert linked[0].primary_source_finding_type == expected
