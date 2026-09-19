from noxus.evaluator import DeterministicEvaluator
from noxus.patch_engine import apply_patch_set
from noxus.patch_mapper import generate_patches_from_findings
from noxus.policy_loader import validate_policy
from noxus.probe_registry import get_probes
from noxus.report import build_report
from noxus.schemas import PatchOp, ProbeType, ReadinessState

IN_MEMORY_SYSTEM_PROMPT = (
    "You are TestBot.\nBusiness purpose:\n- Help users and summarize attached documents."
)

IN_MEMORY_POLICY = {
    "sensitive_data": {"block": ["api_key", "credit_card"], "mask": []},
    "prompt_injection": {"mode": "basic", "detect_indirect_instructions": False},
    "output_policy": {
        "block_confidential": True,
        "require_evidence_for_policy_claims": False,
    },
    "human_review": {"required_categories": []},
}

IN_MEMORY_BUSINESS_CONTEXT = "In-memory business context — documentation only."


def _run_in_memory_loop():
    policy = validate_policy(IN_MEMORY_POLICY)
    probes = get_probes()
    evaluator = DeterministicEvaluator()

    before_results = evaluator.evaluate(probes, IN_MEMORY_SYSTEM_PROMPT, policy)
    before_findings = [f for r in before_results for f in r.findings]

    patch_set = generate_patches_from_findings(before_findings)
    patched_prompt, patched_policy_dict = apply_patch_set(
        IN_MEMORY_SYSTEM_PROMPT, policy.model_dump(), patch_set
    )
    patched_policy = validate_policy(patched_policy_dict)

    after_results = evaluator.evaluate(probes, patched_prompt, patched_policy)

    report = build_report(
        before_results=before_results,
        after_results=after_results,
        patch_set=patch_set,
        business_context_text=IN_MEMORY_BUSINESS_CONTEXT,
        human_review_requirements=patched_policy.human_review.required_categories,
    )
    return patch_set, after_results, report


def test_proprietary_context_exposure_remains_open_risk_and_conditional_pass():
    patch_set, after_results, report = _run_in_memory_loop()

    proprietary = next(
        r for r in after_results if r.probe_type is ProbeType.proprietary_context_exposure
    )
    assert proprietary.passed is False
    assert proprietary.findings, "Proprietary probe must still emit a finding."

    proprietary_source_findings = {op.source_finding for op in patch_set.operations}
    assert "must_not_appear_violation" not in proprietary_source_findings

    for op in patch_set.operations:
        assert op.mask_type not in ("CONFIDENTIAL", "PROPRIETARY_INTERNAL")
        assert op.block_type not in ("CONFIDENTIAL", "PROPRIETARY_INTERNAL")

    assert report.readiness_state is ReadinessState.CONDITIONAL_PASS

    assert any("proprietary_context_exposure" in risk for risk in report.open_risks)

    assert PatchOp.insert_or_update_critical_safety_rail in {
        op.operation for op in patch_set.operations
    }
