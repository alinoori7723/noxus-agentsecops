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


@pytest.mark.parametrize(
    "raw,expected",
    [
        (1.0, "high"),
        (0.9, "high"),
        (0.67, "high"),
        (0.5, "medium"),
        (0.34, "medium"),
        (0.1, "low"),
        (0, "low"),
        ("1.0", "high"),
        ("0.2", "low"),
        ("0", "low"),
    ],
)
def test_semantic_judge_normalizes_numeric_confidence(raw, expected):
    # An IN-RANGE [0,1] probability (or numeric string) is coerced to the nearest
    # strict Confidence bucket. The schema stays strict; nothing is invented.
    out = normalize_semantic_judgment({"confidence": raw})
    assert out["confidence"] == expected


@pytest.mark.parametrize("raw", [-0.1, 1.5, 90, 50, "90%", "1.5", "-0.2", "abc"])
def test_semantic_judge_rejects_out_of_range_confidence_at_boundary(raw):
    # Out-of-range / non-[0,1] / arbitrary values fail FAST at the normalizer
    # boundary (no percentage guessing, no invention, never flow deeper).
    from noxus.errors import SchemaContractError

    with pytest.raises(SchemaContractError):
        normalize_semantic_judgment({"confidence": raw})


def test_semantic_judge_numeric_confidence_validates_end_to_end():
    # A judge response with a float confidence flows through to a valid
    # SemanticJudgment (no SchemaContractError, no loosened schema).
    import json as _json

    from noxus.probe_registry import get_probes

    raw = _json.dumps(
        {
            "probe_id": "p",
            "semantic_violation": True,
            "confidence": 1.0,
            "reason": "followed embedded instructions",
            "suggested_finding_type": "indirect_prompt_injection_semantic",
            "detection_mode": "semantic_llm",
        }
    )
    judgment = SemanticJudgeAgent(FakeLLMProvider(judge=raw), "m").judge(
        get_probes()[0], "resp", [], POLICY, "sys"
    )
    assert judgment.confidence.value == "high"
    assert judgment.semantic_violation is True


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


def test_tuning_prompt_documents_exact_patch_fields():
    # The tuning prompt must show the real per-operation field contract and warn
    # against the plausible-but-invalid vocabularies real models drift into.
    prompt = PolicyTuningAgent(FakeLLMProvider(), "m").build_user_prompt(
        [], POLICY, "sys", ["add_mask_type"]
    )
    assert '"operation":"add_mask_type"' in prompt
    assert '"target":"policy"' in prompt
    assert "prompt_injection.detect_indirect_instructions" in prompt
    for invented in ("'op'", "'control'", "'level'", "'data_type'"):
        assert invented in prompt  # explicitly named as forbidden
    assert "```" not in prompt


def test_judge_prompt_requires_string_confidence_enum():
    prompt = SemanticJudgeAgent(FakeLLMProvider(), "m").build_user_prompt(
        get_probes()[0], "resp", [], POLICY, "sys"
    )
    assert "confidence" in prompt
    assert '"low"' in prompt and '"medium"' in prompt and '"high"' in prompt
    assert "NOT a number" in prompt
    assert "```" not in prompt


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
# Orchestration: Red Team failure degrades to the deterministic baseline (and
# the loop continues) instead of aborting, when baseline findings exist.
# --------------------------------------------------------------------------- #
def _failed_red_report():
    # Red Team garbage -> fallback to deterministic baseline; tuning succeeds.
    provider = FakeLLMProvider(
        red="garbage not json",
        repair="still garbage",
        tuning=m2_data.FULL_REMEDIATION_PATCHSET,
    )
    return run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
    )


def test_agent_assisted_red_failure_preserves_deterministic_baseline_and_continues():
    report = _failed_red_report()
    assert report.before_results, "baseline probes must be preserved"
    assert sum(len(r.findings) for r in report.before_results) > 0
    assert report.metadata.red_team_status == "failed"
    assert report.metadata.fallback_used == "deterministic_baseline"
    assert report.metadata.continued_after_red_failure is True
    # The loop continued: tuning ran and the engine applied real patches.
    assert report.metadata.tuning_iterations >= 1
    assert report.patch_operations_applied


def test_agent_assisted_red_failure_fabricates_no_red_probes():
    report = _failed_red_report()
    baseline_ids = {p.probe_id for p in get_probes()}
    assert set(report.probes_run) == baseline_ids
    assert not any(pid.startswith("agent_") for pid in report.probes_run)


def test_agent_assisted_red_failure_keeps_proprietary_open_risk():
    report = _failed_red_report()
    assert any("proprietary_context_exposure" in r for r in report.open_risks)


def test_agent_assisted_red_failure_response_shows_fallback_not_blank():
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
    # Honest, distinct degraded trace: red failed, judge skipped, tuning used.
    stages = {s["stage"]: s["status"] for s in resp["agent_trace"]["stages"]}
    assert stages["red_team"] == "failed"
    assert stages["semantic_judge"] == "skipped"
    assert stages["policy_tuning"] == "used"
    # The Red-Team failure diagnostics object is present (not schema_failure,
    # since the run continued and did not route to HUMAN_REVIEW_REQUIRED).
    assert resp["schema_failure"] is None
    rtf = resp["red_team_failure"]
    assert rtf["failed_role"] == "red"
    assert rtf["failed_stage"] == "red_team"
    assert rtf["fallback_used"] == "deterministic_baseline"
    assert rtf["continued_after_red_failure"] is True
    assert rtf["baseline_preserved"] is True
    assert resp["agent_trace"]["fallback_used"] == "deterministic_baseline"
    assert sentinel not in json.dumps(resp)
