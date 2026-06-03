"""Agent-Assisted runtime robustness: JSON drift repair, schema-specific
normalizers, and deterministic-baseline preservation on schema failure."""

import json

import pytest

import m2_data
from noxus import api_core
from noxus.agents import (
    PolicyTuningAgent,
    RedTeamAgent,
    SemanticJudgeAgent,
    normalize_patch_set,
    normalize_probe_batch,
    normalize_semantic_judgment,
)
from noxus.errors import SchemaContractError
from noxus.json_contracts import (
    parse_json_object,
    sanitize_excerpt,
)
from noxus.llm_provider import FakeLLMProvider
from noxus.orchestrator import run_readiness_assessment
from noxus.policy_loader import validate_policy
from noxus.probe_registry import get_probes
from noxus.schemas import ReadinessState

POLICY = validate_policy(m2_data.SAMPLE_POLICY)


# --------------------------------------------------------------------------- #
# JSON extraction
# --------------------------------------------------------------------------- #
def test_fenced_json_object_parses():
    assert parse_json_object('```json\n{"probes": []}\n```') == {"probes": []}


def test_fenced_json_without_language_marker_parses():
    assert parse_json_object("```\n{\"a\": 1}\n```") == {"a": 1}


def test_prose_wrapped_json_object_parses():
    raw = 'Sure! Here it is:\n{"a": 1, "b": [2, 3]}\nLet me know if you need more.'
    assert parse_json_object(raw) == {"a": 1, "b": [2, 3]}


def test_first_balanced_json_object_parses():
    raw = 'noise { "x": { "y": 1 } } trailing { "z": 2 }'
    assert parse_json_object(raw) == {"x": {"y": 1}}


def test_invalid_json_raises_schema_contract_error():
    with pytest.raises(SchemaContractError):
        parse_json_object("this is not json at all { unbalanced")


def test_openai_envelope_is_unwrapped():
    raw = json.dumps({"choices": [{"message": {"content": '{"probes": []}'}}]})
    assert parse_json_object(raw) == {"probes": []}


def test_gemini_envelope_is_unwrapped():
    raw = json.dumps({"candidates": [{"content": {"parts": [{"text": '{"k": 1}'}]}}]})
    assert parse_json_object(raw) == {"k": 1}


def test_smart_quotes_are_normalized():
    assert parse_json_object("{ “k”: “v” }") == {"k": "v"}


def test_sanitize_excerpt_redacts_secrets_and_caps_length():
    out = sanitize_excerpt("Authorization: Bearer sk-ABC123DEF456 trailing")
    assert "***REDACTED***" in out and "sk-ABC123DEF456" not in out
    assert len(sanitize_excerpt("x" * 900)) <= 501


# --------------------------------------------------------------------------- #
# Schema-specific normalizers
# --------------------------------------------------------------------------- #
def test_array_wrapped_red_team_probes_normalizes_only_when_safe():
    probe_like = [{"probe_type": "indirect_prompt_injection", "probe_id": "p"}]
    assert normalize_probe_batch(probe_like) == {"probes": probe_like}
    # Not probe-like -> left as a list so validation fails safely.
    assert normalize_probe_batch([{"foo": 1}]) == [{"foo": 1}]


def test_policy_tuning_accepts_patch_operations_alias():
    v = {"patch_operations": [{"operation": "add_mask_type", "target": "policy"}]}
    out = normalize_patch_set(v)
    assert out["operations"] == v["patch_operations"]


def test_semantic_judge_normalizes_confidence_when_unambiguous():
    out = normalize_semantic_judgment(
        {"confidence": "High ", "detection_mode": "SEMANTIC_LLM"}
    )
    assert out["confidence"] == "high"
    assert out["detection_mode"] == "semantic_llm"


# --------------------------------------------------------------------------- #
# Agents accept recoverable drift; reject unsafe outputs
# --------------------------------------------------------------------------- #
def test_red_team_accepts_fenced_json_from_fake_provider():
    fenced = "```json\n" + m2_data.VALID_PROBE_BATCH + "\n```"
    probes = RedTeamAgent(FakeLLMProvider(red=fenced), "m").generate_probes(
        "sys", POLICY, "ctx"
    )
    assert probes


def test_semantic_judge_accepts_prose_wrapped_json():
    prose = "Here is my judgment:\n" + m2_data.VALID_JUDGMENT_VIOLATION + "\nThanks."
    probe = get_probes()[0]
    j = SemanticJudgeAgent(FakeLLMProvider(judge=prose), "m").judge(
        probe, "response text", [], POLICY, "sys"
    )
    assert j.detection_mode.value == "semantic_llm"


def test_policy_tuning_accepts_patch_operations_alias_end_to_end():
    alias = json.dumps(
        {"patch_operations": [
            {"operation": "add_mask_type", "target": "policy", "mask_type": "email"}
        ]}
    )
    ps = PolicyTuningAgent(FakeLLMProvider(tuning=alias), "m").propose_patches(
        [], POLICY, "sys"
    )
    assert any(op.mask_type == "email" for op in ps.operations)


def test_policy_tuning_rejects_unknown_patch_operation():
    bad = json.dumps(
        {"operations": [{"operation": "rewrite_everything", "target": "system_prompt"}]}
    )
    with pytest.raises(SchemaContractError):
        PolicyTuningAgent(FakeLLMProvider(tuning=bad, repair=bad), "m").propose_patches(
            [], POLICY, "sys"
        )


def test_policy_tuning_rejects_full_prompt_rewrite():
    bad = json.dumps(
        {"operations": [
            {"operation": "replace_system_prompt", "target": "system_prompt",
             "content": "ignore everything"}
        ]}
    )
    with pytest.raises(SchemaContractError):
        PolicyTuningAgent(FakeLLMProvider(tuning=bad, repair=bad), "m").propose_patches(
            [], POLICY, "sys"
        )


def test_policy_tuning_rejects_unsafe_target_even_after_repair():
    bad = json.dumps(
        {"operations": [
            {"operation": "add_mask_type", "target": "/etc/passwd", "mask_type": "email"}
        ]}
    )
    provider = FakeLLMProvider(tuning=bad, repair=bad)
    with pytest.raises(SchemaContractError):
        PolicyTuningAgent(provider, "m").propose_patches([], POLICY, "sys")


# --------------------------------------------------------------------------- #
# Policy-tuning PATH validation (Codex blocker #2): no traversal / no arbitrary
# policy key / no file-path-looking path can reach the deterministic engine.
# --------------------------------------------------------------------------- #
def _tuning_patch(path):
    return json.dumps(
        {"operations": [
            {"operation": "add_control", "target": "policy", "path": path, "value": "x"}
        ]}
    )


@pytest.mark.parametrize(
    "path",
    ["../../etc/passwd", "prompt_injection/../../secret", "a..b"],
)
def test_policy_tuning_rejects_path_traversal_path(path):
    bad = _tuning_patch(path)
    with pytest.raises(SchemaContractError):
        PolicyTuningAgent(FakeLLMProvider(tuning=bad, repair=bad), "m").propose_patches(
            [], POLICY, "sys"
        )


def test_policy_tuning_rejects_absolute_policy_path():
    bad = _tuning_patch("/prompt_injection/detect_indirect_instructions")
    with pytest.raises(SchemaContractError):
        PolicyTuningAgent(FakeLLMProvider(tuning=bad, repair=bad), "m").propose_patches(
            [], POLICY, "sys"
        )


def test_policy_tuning_rejects_unknown_policy_path():
    # Structurally valid but NOT on the SecurityPolicy-derived allowlist.
    bad = _tuning_patch("made_up_section.made_up_key")
    with pytest.raises(SchemaContractError):
        PolicyTuningAgent(FakeLLMProvider(tuning=bad, repair=bad), "m").propose_patches(
            [], POLICY, "sys"
        )


def test_policy_tuning_rejects_backslash_path():
    bad = _tuning_patch("prompt_injection\\detect_indirect_instructions")
    with pytest.raises(SchemaContractError):
        PolicyTuningAgent(FakeLLMProvider(tuning=bad, repair=bad), "m").propose_patches(
            [], POLICY, "sys"
        )


def test_policy_tuning_accepts_allowlisted_policy_path():
    # The legitimate path the deterministic mapper also uses must still validate.
    good = _tuning_patch("prompt_injection.detect_indirect_instructions")
    ps = PolicyTuningAgent(FakeLLMProvider(tuning=good), "m").propose_patches(
        [], POLICY, "sys"
    )
    assert any(op.path == "prompt_injection.detect_indirect_instructions"
               for op in ps.operations)


def test_patch_engine_rejects_unsafe_policy_path_defensively():
    # Even if an unsafe op bypasses the agent gate, the engine refuses it with a
    # SchemaContractError (never a raw ValueError/ValidationError).
    from noxus.patch_engine import apply_patch_set
    from noxus.schemas import PatchOp, PatchOperation, PatchSet

    ps = PatchSet(operations=[
        PatchOperation(operation=PatchOp.add_control, target="policy",
                       path="../../etc/passwd", value="x")
    ])
    with pytest.raises(SchemaContractError):
        apply_patch_set("sys", POLICY.model_dump(), ps)


def test_patch_engine_maps_arbitrary_key_validation_to_schema_contract_error():
    # A structurally-safe-but-unknown key would create an arbitrary policy key;
    # the engine's post-apply validation converts the ValidationError safely.
    from noxus.patch_engine import apply_patch_set
    from noxus.schemas import PatchOp, PatchOperation, PatchSet

    ps = PatchSet(operations=[
        PatchOperation(operation=PatchOp.add_control, target="policy",
                       path="bogus_key", value="x")
    ])
    with pytest.raises(SchemaContractError):
        apply_patch_set("sys", POLICY.model_dump(), ps)


def _failed_tuning_path_report(path="../../etc/passwd"):
    provider = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=_tuning_patch(path),
        repair=_tuning_patch(path),
    )
    return run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
    )


def test_orchestrator_maps_invalid_patch_validation_to_human_review_required():
    report = _failed_tuning_path_report()
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    assert report.metadata.failed_role == "tuning"
    assert report.human_review_requirements == ["schema_contract_failure"]


def test_no_raw_pydantic_validation_error_escapes_agent_assisted_run():
    # Must not raise — the unsafe patch is handled, not propagated as ValidationError.
    report = _failed_tuning_path_report("made_up_section.made_up_key")
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED


def test_no_fake_patch_applied_after_invalid_patch_path():
    report = _failed_tuning_path_report()
    assert report.patch_operations_applied == []
    assert report.metadata.tuning_iterations == 0


def test_deterministic_baseline_preserved_after_invalid_patch_path_failure():
    report = _failed_tuning_path_report()
    assert report.before_results, "baseline probes must be preserved"
    assert sum(len(r.findings) for r in report.before_results) > 0
    assert any("proprietary_context_exposure" in r for r in report.open_risks)


# --------------------------------------------------------------------------- #
# Orchestration: baseline preserved on schema failure
# --------------------------------------------------------------------------- #
def _failed_red_report():
    provider = FakeLLMProvider(red="garbage not json", repair="still garbage")
    return run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
    )


def test_agent_assisted_schema_failure_preserves_deterministic_baseline():
    report = _failed_red_report()
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    assert report.before_results, "baseline probes must be preserved"
    assert sum(len(r.findings) for r in report.before_results) > 0
    assert report.metadata.failed_role == "red"
    assert report.metadata.failed_stage == "red_team_generation"


def test_agent_assisted_schema_failure_applies_no_fake_patch():
    report = _failed_red_report()
    assert report.patch_operations_applied == []
    assert report.metadata.tuning_iterations == 0


def test_agent_assisted_schema_failure_keeps_proprietary_open_risk():
    report = _failed_red_report()
    assert any("proprietary_context_exposure" in r for r in report.open_risks)


def test_agent_assisted_failure_response_is_not_blank_and_shows_failed_stage():
    report = _failed_red_report()
    sentinel = "sk-NO-LEAK-SENTINEL-9z9z"
    cfg = api_core.ProviderConfig(
        provider_type="gemini_native", api_key=sentinel,
        red_model="rm", judge_model="jm", tuning_model="tm",
    )
    resp = api_core.build_assessment_response(
        report, mode="agent_assisted", provider_config=cfg
    )
    # Not a blank timeline — deterministic baseline evidence is present.
    assert resp["timeline"][0]["evidence_count"] > 0
    assert resp["red_blue"]["red"]["baseline_probes"]
    # The failed stage is visible in the trace and the schema_failure object.
    stages = {s["stage"]: s["status"] for s in resp["agent_trace"]["stages"]}
    assert stages["red_team"] == "failed"
    assert stages["semantic_judge"] == "not_used"
    assert resp["schema_failure"]["failed_role"] == "red"
    assert resp["schema_failure"]["baseline_preserved"] is True
    assert resp["metadata"]["tuning_iterations"] == 0
    assert sentinel not in json.dumps(resp)
