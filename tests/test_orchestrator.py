import m2_data
from noxus.constants import MAX_TUNING_ITERATIONS
from noxus.llm_provider import FakeLLMProvider
from noxus.orchestrator import run_readiness_assessment
from noxus.probe_registry import get_probes
from noxus.schemas import ProbeType, ReadinessState


def _agent_assisted(provider):
    return run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
    )


def test_deterministic_mode_preserves_milestone_1_behavior():
    report = run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="deterministic",
    )
    assert report.metadata.mode == "deterministic"
    assert report.before_score == 0
    assert report.after_score == 90
    assert report.readiness_state is ReadinessState.CONDITIONAL_PASS

    indirect_before = next(
        r for r in report.before_results
        if r.probe_type is ProbeType.indirect_prompt_injection
    )
    indirect_after = next(
        r for r in report.after_results
        if r.probe_type is ProbeType.indirect_prompt_injection
    )
    assert indirect_before.passed is False
    assert indirect_after.passed is True
    assert any("proprietary_context_exposure" in risk for risk in report.open_risks)


def test_agent_assisted_mode_keeps_deterministic_baseline_probes():
    provider = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.EMPTY_PATCHSET,
    )
    report = _agent_assisted(provider)
    baseline_ids = {p.probe_id for p in get_probes()}
    assert baseline_ids.issubset(set(report.probes_run))
    assert report.metadata.mode == "agent_assisted"


def test_agent_assisted_mode_enforces_max_tuning_iterations():
    # Empty patches never resolve findings, so the loop runs to the ceiling.
    provider = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.EMPTY_PATCHSET,
    )
    report = _agent_assisted(provider)
    assert MAX_TUNING_ITERATIONS == 2
    assert report.metadata.tuning_iterations == MAX_TUNING_ITERATIONS


def test_agent_schema_failure_returns_human_review_required():
    provider = FakeLLMProvider(red=m2_data.INVALID_JSON, repair=m2_data.INVALID_JSON)
    report = _agent_assisted(provider)
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    # No dirty continuation with partial state.
    assert report.after_results == []
    assert report.patch_operations_applied == []


def test_agent_assisted_mode_does_not_fake_proprietary_context_pass():
    # Even if the tuning agent tries to "fix" proprietary exposure and the judge
    # reports no violation, the deterministic finding must remain.
    provider = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.PATCHSET_PROPRIETARY_ATTEMPT,
    )
    report = _agent_assisted(provider)
    proprietary = [
        r for r in report.after_results
        if r.probe_type is ProbeType.proprietary_context_exposure
    ]
    assert proprietary
    assert all(not r.passed for r in proprietary)
    assert any("proprietary_context_exposure" in risk for risk in report.open_risks)
    assert report.readiness_state is not ReadinessState.PASS


def test_orchestrator_aborts_further_llm_execution_after_schema_contract_error():
    provider = FakeLLMProvider(red=m2_data.INVALID_JSON, repair=m2_data.INVALID_JSON)
    report = _agent_assisted(provider)
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    # The judge and tuning agents must never have been called.
    assert all("[NOXUS_JUDGE]" not in c["system_prompt"] for c in provider.calls)
    assert all("[NOXUS_TUNING]" not in c["system_prompt"] for c in provider.calls)
