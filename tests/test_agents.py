import pytest

import m2_data
from noxus.agents import PolicyTuningAgent, RedTeamAgent, SemanticJudgeAgent
from noxus.errors import SchemaContractError
from noxus.llm_provider import FakeLLMProvider
from noxus.orchestrator import run_readiness_assessment
from noxus.schemas import (
    DetectionMode,
    PatchSet,
    Probe,
    ProbeType,
    ReadinessState,
    SecurityPolicy,
    SemanticJudgment,
)


def _policy() -> SecurityPolicy:
    return SecurityPolicy.model_validate(m2_data.SAMPLE_POLICY)


# --- Red Team Agent ---
def test_red_team_agent_outputs_schema_valid_probes_with_fake_provider():
    provider = FakeLLMProvider(red=m2_data.VALID_PROBE_BATCH)
    agent = RedTeamAgent(provider, "red-model")
    probes = agent.generate_probes(
        m2_data.SAMPLE_SYSTEM_PROMPT, _policy(), m2_data.SAMPLE_BUSINESS_CONTEXT
    )
    assert probes
    assert all(isinstance(p, Probe) for p in probes)
    assert any(p.probe_type is ProbeType.indirect_prompt_injection for p in probes)


def test_red_team_agent_requires_indirect_injection_probe():
    # Real contract #1: the outgoing prompt template MANDATES indirect injection.
    provider = FakeLLMProvider(red=m2_data.VALID_PROBE_BATCH)
    agent = RedTeamAgent(provider, "red-model")
    prompt = agent.build_user_prompt(
        m2_data.SAMPLE_SYSTEM_PROMPT,
        _policy(),
        m2_data.SAMPLE_BUSINESS_CONTEXT,
        ["indirect_prompt_injection", "pii_leakage"],
    )
    assert (
        "You MUST include at least one probe of type indirect_prompt_injection"
        in prompt
    )


def test_red_team_agent_rejects_probe_list_without_indirect_injection():
    # Real contract #2: the validation layer rejects an otherwise schema-valid
    # probe list that lacks an indirect_prompt_injection probe.
    provider = FakeLLMProvider(
        red=m2_data.PROBE_BATCH_NO_INDIRECT,
        repair=m2_data.PROBE_BATCH_NO_INDIRECT,
    )
    agent = RedTeamAgent(provider, "red-model")
    with pytest.raises(SchemaContractError):
        agent.generate_probes(
            m2_data.SAMPLE_SYSTEM_PROMPT, _policy(), m2_data.SAMPLE_BUSINESS_CONTEXT
        )


# --- Policy Tuning Agent ---
def test_policy_tuning_agent_outputs_schema_valid_patchset():
    provider = FakeLLMProvider(tuning=m2_data.EMPTY_PATCHSET)
    agent = PolicyTuningAgent(provider, "tune-model")
    patch_set = agent.propose_patches([], _policy(), m2_data.SAMPLE_SYSTEM_PROMPT)
    assert isinstance(patch_set, PatchSet)


def test_policy_tuning_agent_does_not_apply_patches():
    provider = FakeLLMProvider(tuning=m2_data.PATCHSET_WITH_RAIL)
    agent = PolicyTuningAgent(provider, "tune-model")
    policy = _policy()
    policy_before = policy.model_dump()
    prompt = m2_data.SAMPLE_SYSTEM_PROMPT

    patch_set = agent.propose_patches([], policy, prompt)

    # The agent proposes operations but applies nothing.
    assert isinstance(patch_set, PatchSet)
    assert len(patch_set.operations) == 1
    assert policy.model_dump() == policy_before  # input policy untouched
    assert "[CRITICAL_SAFETY_RAILS]" not in prompt  # prompt never edited here


# --- Semantic Judge Agent ---
def test_semantic_judge_outputs_schema_valid_judgment():
    provider = FakeLLMProvider(judge=m2_data.VALID_JUDGMENT_VIOLATION)
    agent = SemanticJudgeAgent(provider, "judge-model")
    probe = Probe(
        probe_id="probe_indirect",
        probe_type=ProbeType.indirect_prompt_injection,
        detection_mode=DetectionMode.deterministic_simulation,
        description="d",
    )
    judgment = agent.judge(probe, "some response", [], _policy(), "system prompt")
    assert isinstance(judgment, SemanticJudgment)
    assert judgment.detection_mode is DetectionMode.semantic_llm


def test_semantic_judge_failure_degrades_and_continues_to_tuning():
    # Red team succeeds, but the semantic judge output is unrecoverable. The loop
    # DEGRADES (drops the semantic supplement) and continues to tuning on the
    # deterministic + valid red-team evidence — it does NOT abort.
    provider = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.INVALID_JSON,
        repair=m2_data.INVALID_JSON,
        tuning=m2_data.FULL_REMEDIATION_PATCHSET,
    )
    report = run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
    )
    # Judge recorded as failed; loop continued (tuning ran, patches applied).
    assert report.metadata.semantic_judge_status == "failed"
    assert report.metadata.evidence_basis == "red_team_augmented"
    assert report.metadata.tuning_iterations >= 1
    assert report.patch_operations_applied
    # Baseline preserved; no semantic finding fabricated despite the failure.
    assert report.before_results
    assert not any(
        f.detection_mode is DetectionMode.semantic_llm
        for r in report.after_results
        for f in r.findings
    )
