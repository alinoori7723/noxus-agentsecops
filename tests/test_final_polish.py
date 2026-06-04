"""Final-polish review tests:

* Judge/Tuning/patch-application fallback symmetry (task 3)
* Confidence-normalizer edge-case hardening (task 4)
* Markdown/JSON repair regression guards for every role (task 5)
* Evidence-basis trace clarity for degraded/fallback runs (task 6)

All run against FakeLLMProvider — no network, no real credentials.
"""

import json
import math

import pytest

import m2_data
from noxus import api_core
from noxus.agents import (
    PolicyTuningAgent,
    RedTeamAgent,
    SemanticJudgeAgent,
    normalize_semantic_judgment,
)
from noxus.errors import SchemaContractError
from noxus.json_contracts import parse_json_object
from noxus.llm_provider import FakeLLMProvider
from noxus.orchestrator import run_readiness_assessment
from noxus.policy_loader import validate_policy
from noxus.probe_registry import get_probes
from noxus.schemas import DetectionMode, ReadinessState

POLICY = validate_policy(m2_data.SAMPLE_POLICY)
_SENTINEL = "sk-SENTINEL-final-polish-DONOTLEAK-zzz"


def _run(provider):
    return run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
    )


def _judge_json(confidence):
    return json.dumps(
        {
            "probe_id": "p",
            "semantic_violation": True,
            "confidence": confidence,
            "reason": "r",
            "suggested_finding_type": "indirect_prompt_injection_semantic",
            "detection_mode": "semantic_llm",
        }
    )


# A tuning patch that PASSES the agent safe-gate (allowlisted path) but FAILS at
# deterministic patch application (bool policy field receives a non-bool) — used
# to exercise the patch_application stage specifically.
_BAD_APPLY_PATCHSET = json.dumps(
    {
        "operations": [
            {
                "operation": "set_control_level",
                "target": "policy",
                "path": "prompt_injection.detect_indirect_instructions",
                "value": "strict",
            }
        ]
    }
)


# --------------------------------------------------------------------------- #
# Task 3 — Judge / Tuning / patch-application fallback symmetry
# --------------------------------------------------------------------------- #
def test_semantic_judge_failure_preserves_baseline_and_continues_to_tuning_when_baseline_findings_exist():
    report = _run(
        FakeLLMProvider(
            red=m2_data.VALID_PROBE_BATCH,
            judge=m2_data.INVALID_JSON,
            repair=m2_data.INVALID_JSON,
            tuning=m2_data.FULL_REMEDIATION_PATCHSET,
        )
    )
    assert report.before_results, "baseline preserved"
    assert sum(len(r.findings) for r in report.before_results) > 0
    assert report.metadata.semantic_judge_status == "failed"
    assert report.metadata.tuning_iterations >= 1
    assert report.patch_operations_applied
    # No fabricated semantic findings despite the judge failure.
    assert not any(
        f.detection_mode is DetectionMode.semantic_llm
        for r in report.after_results
        for f in r.findings
    )


def test_semantic_judge_failure_records_failed_role_and_fallback_basis():
    report = _run(
        FakeLLMProvider(
            red=m2_data.VALID_PROBE_BATCH,
            judge=m2_data.INVALID_JSON,
            repair=m2_data.INVALID_JSON,
            tuning=m2_data.FULL_REMEDIATION_PATCHSET,
        )
    )
    assert report.metadata.semantic_judge_status == "failed"
    assert report.metadata.evidence_basis == "red_team_augmented"
    resp = api_core.build_assessment_response(report, mode="agent_assisted")
    sjf = resp["semantic_judge_failure"]
    assert sjf and sjf["failed_role"] == "judge" and sjf["failed_stage"] == "semantic_judge"
    assert sjf["fallback_basis"] == "red_team_augmented"
    stages = {s["stage"]: s["status"] for s in resp["agent_trace"]["stages"]}
    assert stages["semantic_judge"] == "failed"


def test_tuning_failure_preserves_baseline_and_prior_agent_trace():
    report = _run(
        FakeLLMProvider(
            red=m2_data.VALID_PROBE_BATCH,
            judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
            tuning=m2_data.INVALID_JSON,
            repair=m2_data.INVALID_JSON,
        )
    )
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    assert report.before_results, "baseline preserved"
    assert report.metadata.failed_role == "tuning"
    resp = api_core.build_assessment_response(report, mode="agent_assisted")
    stages = {s["stage"]: s["status"] for s in resp["agent_trace"]["stages"]}
    # Prior stages stay visible: red used, judge used (it ran), tuning failed.
    assert stages["red_team"] == "used"
    assert stages["semantic_judge"] in ("used", "not_used")
    assert stages["policy_tuning"] == "failed"


def test_tuning_failure_returns_human_review_required_without_fake_patch():
    report = _run(
        FakeLLMProvider(
            red=m2_data.VALID_PROBE_BATCH,
            judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
            tuning=m2_data.INVALID_JSON,
            repair=m2_data.INVALID_JSON,
        )
    )
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    assert report.human_review_requirements == ["schema_contract_failure"]
    assert report.patch_operations_applied == []
    assert report.metadata.tuning_iterations == 0


def test_patch_application_failure_preserves_baseline_and_maps_to_human_review_required():
    # The patch PASSES the agent safe-gate but FAILS deterministic application; it
    # must map to HUMAN_REVIEW_REQUIRED (never a raw ValidationError) with the
    # baseline preserved and the failure attributed to the tuning role.
    report = _run(
        FakeLLMProvider(
            red=m2_data.VALID_PROBE_BATCH,
            judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
            tuning=_BAD_APPLY_PATCHSET,
            repair=_BAD_APPLY_PATCHSET,
        )
    )
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    assert report.metadata.failed_stage == "patch_application"
    assert report.metadata.failed_role == "tuning"
    assert report.before_results, "baseline preserved"
    assert report.patch_operations_applied == []


def test_no_blank_timeline_for_judge_or_tuning_failure():
    for provider in (
        FakeLLMProvider(  # judge degrade
            red=m2_data.VALID_PROBE_BATCH,
            judge=m2_data.INVALID_JSON,
            repair=m2_data.INVALID_JSON,
            tuning=m2_data.FULL_REMEDIATION_PATCHSET,
        ),
        FakeLLMProvider(  # tuning abort
            red=m2_data.VALID_PROBE_BATCH,
            judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
            tuning=m2_data.INVALID_JSON,
            repair=m2_data.INVALID_JSON,
        ),
    ):
        report = _run(provider)
        resp = api_core.build_assessment_response(report, mode="agent_assisted")
        # Baseline evidence is present in the timeline (never a blank run).
        assert resp["timeline"][0]["evidence_count"] > 0
        assert resp["red_blue"]["red"]["baseline_probes"]


# --------------------------------------------------------------------------- #
# Task 4 — confidence-normalizer hardening
# --------------------------------------------------------------------------- #
def test_judge_confidence_accepts_1_as_high_or_equivalent_documented_value():
    assert normalize_semantic_judgment({"confidence": 1})["confidence"] == "high"
    assert normalize_semantic_judgment({"confidence": 1.0})["confidence"] == "high"
    j = SemanticJudgeAgent(FakeLLMProvider(judge=_judge_json(1.0)), "m").judge(
        get_probes()[0], "resp", [], POLICY, "sys"
    )
    assert j.confidence.value == "high"


def test_judge_confidence_accepts_0_as_low_or_equivalent_documented_value():
    assert normalize_semantic_judgment({"confidence": 0})["confidence"] == "low"
    assert normalize_semantic_judgment({"confidence": 0.0})["confidence"] == "low"
    j = SemanticJudgeAgent(FakeLLMProvider(judge=_judge_json(0)), "m").judge(
        get_probes()[0], "resp", [], POLICY, "sys"
    )
    assert j.confidence.value == "low"


@pytest.mark.parametrize("bad", [-0.1, -1, -0.0001])
def test_judge_confidence_rejects_negative_at_normalizer_boundary(bad):
    with pytest.raises(SchemaContractError):
        normalize_semantic_judgment({"confidence": bad})


@pytest.mark.parametrize("bad", [1.0001, 1.5, 2, 90, 100])
def test_judge_confidence_rejects_above_one_at_normalizer_boundary(bad):
    with pytest.raises(SchemaContractError):
        normalize_semantic_judgment({"confidence": bad})


def test_judge_confidence_rejects_nan_at_normalizer_boundary():
    with pytest.raises(SchemaContractError):
        normalize_semantic_judgment({"confidence": float("nan")})


def test_judge_confidence_rejects_infinity_at_normalizer_boundary():
    with pytest.raises(SchemaContractError):
        normalize_semantic_judgment({"confidence": float("inf")})
    with pytest.raises(SchemaContractError):
        normalize_semantic_judgment({"confidence": float("-inf")})


@pytest.mark.parametrize("bad", [True, False])
def test_judge_confidence_rejects_bool_at_normalizer_boundary(bad):
    with pytest.raises(SchemaContractError):
        normalize_semantic_judgment({"confidence": bad})


@pytest.mark.parametrize("bad", ["definitely", "90%", "1.5", "", "high-ish"])
def test_judge_confidence_rejects_arbitrary_string_at_normalizer_boundary(bad):
    with pytest.raises(SchemaContractError):
        normalize_semantic_judgment({"confidence": bad})


@pytest.mark.parametrize("bad", [[0.9], {"x": 1}, None])
def test_judge_confidence_rejects_array_or_object_at_normalizer_boundary(bad):
    with pytest.raises(SchemaContractError):
        normalize_semantic_judgment({"confidence": bad})


@pytest.mark.parametrize("bad", [-0.1, 1.5, float("nan"), float("inf"), "definitely", [0.9], {"x": 1}, True])
def test_rejection_maps_to_schema_contract_error_or_human_review_required(bad):
    # End-to-end: an invalid confidence (with the repair also invalid) surfaces
    # as SchemaContractError at the agent boundary — never a raw exception.
    provider = FakeLLMProvider(judge=_judge_json(bad), repair=_judge_json(bad))
    with pytest.raises(SchemaContractError):
        SemanticJudgeAgent(provider, "m").judge(
            get_probes()[0], "resp", [], POLICY, "sys"
        )


# --------------------------------------------------------------------------- #
# Task 5 — markdown / JSON repair regression guards (all roles)
# --------------------------------------------------------------------------- #
def _fenced(payload):
    return "```json\n" + payload + "\n```"


def test_red_team_accepts_markdown_fenced_json():
    probes = RedTeamAgent(
        FakeLLMProvider(red=_fenced(m2_data.VALID_PROBE_BATCH)), "m"
    ).generate_probes("sys", POLICY, "ctx")
    assert probes


def test_semantic_judge_accepts_markdown_fenced_json():
    j = SemanticJudgeAgent(
        FakeLLMProvider(judge=_fenced(m2_data.VALID_JUDGMENT_VIOLATION)), "m"
    ).judge(get_probes()[0], "resp", [], POLICY, "sys")
    assert j.detection_mode.value == "semantic_llm"


def test_policy_tuning_accepts_markdown_fenced_json():
    ps = PolicyTuningAgent(
        FakeLLMProvider(tuning=_fenced(m2_data.PATCHSET_WITH_RAIL)), "m"
    ).propose_patches([], POLICY, "sys")
    assert ps.operations


def test_markdown_repair_does_not_allow_extra_root_fields():
    fenced_bad = _fenced(m2_data.PROBE_BATCH_EXTRA_ROOT_FIELD)
    with pytest.raises(SchemaContractError):
        RedTeamAgent(
            FakeLLMProvider(red=fenced_bad, repair=fenced_bad), "m"
        ).generate_probes("sys", POLICY, "ctx")


def test_markdown_repair_does_not_allow_unsafe_policy_paths():
    fenced_bad = _fenced(
        json.dumps(
            {"operations": [
                {"operation": "add_control", "target": "policy",
                 "path": "../../etc/passwd", "value": "x"}
            ]}
        )
    )
    with pytest.raises(SchemaContractError):
        PolicyTuningAgent(
            FakeLLMProvider(tuning=fenced_bad, repair=fenced_bad), "m"
        ).propose_patches([], POLICY, "sys")


# --------------------------------------------------------------------------- #
# Issue 3 — multi-block markdown: ALWAYS bind to the FIRST balanced JSON object;
# never skip an unsafe/invalid first block to reach a clean later block.
# --------------------------------------------------------------------------- #
def _two_blocks(first: str, second: str) -> str:
    return (
        "Here is my answer:\n\n"
        f"```json\n{first}\n```\n\n"
        "and an alternative:\n\n"
        f"```json\n{second}\n```\n"
    )


_EXTRA_ROOT_PROBE_BATCH = json.dumps(
    {
        "probes": [
            {"probe_id": "p1", "probe_type": "indirect_prompt_injection",
             "detection_mode": "deterministic_simulation", "description": "x"}
        ],
        "status": "PASS",  # forbidden extra root field
    }
)
_UNSAFE_PATH_PATCHSET = json.dumps(
    {"operations": [
        {"operation": "add_control", "target": "policy",
         "path": "../../etc/passwd", "value": "x"}
    ]}
)


def test_markdown_multi_block_uses_first_balanced_json_object():
    raw = _two_blocks('{"a": 1}', '{"a": 2}')
    assert parse_json_object(raw) == {"a": 1}


def test_markdown_multi_block_rejects_if_first_json_has_extra_root_fields():
    raw = _two_blocks(_EXTRA_ROOT_PROBE_BATCH, m2_data.VALID_PROBE_BATCH)
    with pytest.raises(SchemaContractError):
        RedTeamAgent(FakeLLMProvider(red=raw, repair=raw), "m").generate_probes(
            "sys", POLICY, "ctx"
        )


def test_markdown_multi_block_rejects_if_first_json_has_unsafe_policy_path():
    raw = _two_blocks(_UNSAFE_PATH_PATCHSET, m2_data.PATCHSET_WITH_RAIL)
    with pytest.raises(SchemaContractError):
        PolicyTuningAgent(FakeLLMProvider(tuning=raw, repair=raw), "m").propose_patches(
            [], POLICY, "sys"
        )


def test_markdown_multi_block_does_not_skip_unsafe_first_block_to_accept_safe_second_block():
    # First block is schema-invalid (extra root field); the clean second block
    # MUST NOT be silently used instead -> the contract fails.
    raw = _two_blocks(_EXTRA_ROOT_PROBE_BATCH, m2_data.VALID_PROBE_BATCH)
    # The first balanced object is the unsafe one (proves no skipping).
    assert "status" in parse_json_object(raw)
    with pytest.raises(SchemaContractError):
        RedTeamAgent(FakeLLMProvider(red=raw, repair=raw), "m").generate_probes(
            "sys", POLICY, "ctx"
        )


def test_markdown_multi_block_safe_first_block_accepted_even_if_later_block_exists():
    # A valid first block is accepted; a noisy/invalid later block is irrelevant.
    raw = _two_blocks(m2_data.VALID_PROBE_BATCH, '{"garbage": true, "status": "PASS"}')
    probes = RedTeamAgent(FakeLLMProvider(red=raw), "m").generate_probes(
        "sys", POLICY, "ctx"
    )
    assert probes
    assert any(p.probe_type.value == "indirect_prompt_injection" for p in probes)


# --------------------------------------------------------------------------- #
# Task 6 — evidence-basis trace clarity
# --------------------------------------------------------------------------- #
def test_degraded_fallback_report_has_evidence_basis():
    report = _run(
        FakeLLMProvider(
            red=m2_data.INVALID_JSON,
            repair=m2_data.INVALID_JSON,
            tuning=m2_data.FULL_REMEDIATION_PATCHSET,
        )
    )
    assert report.metadata.evidence_basis == "degraded_fallback"
    resp = api_core.build_assessment_response(report, mode="agent_assisted")
    assert resp["metadata"]["evidence_basis"] == "degraded_fallback"
    assert resp["agent_trace"]["evidence_basis"] == "degraded_fallback"


def test_normal_agent_run_does_not_show_fallback_basis():
    report = _run(
        FakeLLMProvider(
            red=m2_data.VALID_PROBE_BATCH,
            judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
            tuning=m2_data.EMPTY_PATCHSET,
        )
    )
    assert report.metadata.evidence_basis == "red_team_augmented"
    resp = api_core.build_assessment_response(report, mode="agent_assisted")
    assert resp["agent_trace"]["evidence_basis"] == "red_team_augmented"
    assert resp["agent_trace"]["continued_after_red_failure"] is False
    assert resp["red_team_failure"] is None


def test_deterministic_run_evidence_basis_is_deterministic_baseline():
    report = run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="deterministic",
    )
    assert report.metadata.evidence_basis == "deterministic_baseline"


def test_provider_test_never_echoes_api_key_final_polish():
    # Defensive: the provider connectivity test never returns the key.
    fake = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_VIOLATION,
        tuning=m2_data.EMPTY_PATCHSET,
    )
    import noxus.api_core as core

    orig = core.build_provider
    core.build_provider = lambda cfg: (fake, {"red_model": "r", "judge_model": "j", "tuning_model": "t"})
    try:
        res = core.test_provider(
            core.ProviderConfig(provider_type="gemini_native", api_key=_SENTINEL),
            ["red", "judge", "tuning"],
        )
    finally:
        core.build_provider = orig
    assert _SENTINEL not in json.dumps(res)
