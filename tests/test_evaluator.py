from noxus.constants import INDIRECT_INJECTION_MARKERS
from noxus.evaluator import DeterministicEvaluator, evaluate_probe_response
from noxus.probe_registry import get_probes
from noxus.schemas import (
    DetectionMode,
    Probe,
    ProbeType,
    SecurityPolicy,
)


def _probe(ptype=ProbeType.policy_conflict_probe, must_not_appear=None):
    return Probe(
        probe_id="p_test",
        probe_type=ptype,
        detection_mode=DetectionMode.deterministic,
        description="test probe",
        must_not_appear_in_output=must_not_appear or [],
    )


def test_deterministic_evaluator_flags_indirect_injection_markers():
    response = " ".join(INDIRECT_INJECTION_MARKERS)
    findings = evaluate_probe_response(_probe(), response)
    indirect = [f for f in findings if f.finding_type == "indirect_prompt_injection_simulated"]
    assert len(indirect) == 1
    f = indirect[0]
    assert f.severity.value == "high"
    assert f.detection_mode is DetectionMode.deterministic_simulation
    assert f.evidence_source == "deterministic_marker"
    assert "system_prompt" in f.remediation_target
    assert "security_policy" in f.remediation_target


def test_deterministic_evaluator_flags_fake_secret():
    findings = evaluate_probe_response(_probe(), "key: sk-FAKE1234567890abcdefSECRET")
    assert any(f.finding_type == "fake_secret_exfiltration" for f in findings)


def test_deterministic_evaluator_flags_pii():
    findings = evaluate_probe_response(
        _probe(), "email jane.doe@example.com phone 415-555-0142"
    )
    assert any(f.finding_type == "pii_leakage" for f in findings)


def test_deterministic_evaluator_respects_must_not_appear():
    probe = _probe(must_not_appear=["CONFIDENTIAL"])
    findings = evaluate_probe_response(probe, "this is CONFIDENTIAL material")
    assert any(f.finding_type == "must_not_appear_violation" for f in findings)


def test_cli_before_state_fails_indirect_injection_simulation():
    evaluator = DeterministicEvaluator()
    results = evaluator.evaluate(get_probes(), "You are a bot.", SecurityPolicy())
    indirect = next(
        r for r in results if r.probe_type is ProbeType.indirect_prompt_injection
    )
    assert indirect.passed is False
    assert any(
        f.finding_type == "indirect_prompt_injection_simulated" for f in indirect.findings
    )
