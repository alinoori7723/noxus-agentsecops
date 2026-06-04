import pytest

import m2_data
from noxus.errors import SchemaContractError
from noxus.json_contracts import (
    load_validated_object,
    parse_json_object,
    validate_model_object,
)
from noxus.llm_provider import FakeLLMProvider
from noxus.orchestrator import run_readiness_assessment
from noxus.schemas import ProbeBatch, ReadinessState


def test_json_contract_accepts_valid_probe_json():
    # A provider that would raise if any repair were attempted.
    provider = FakeLLMProvider()
    obj = load_validated_object(
        provider, "m", m2_data.VALID_PROBE_BATCH, ProbeBatch, "ProbeBatch"
    )
    assert isinstance(obj, ProbeBatch)
    assert obj.probes
    assert provider.calls == []  # no repair was needed


def test_json_contract_rejects_invalid_json_after_one_repair():
    provider = FakeLLMProvider(repair=m2_data.INVALID_JSON)
    with pytest.raises(SchemaContractError):
        load_validated_object(
            provider, "m", m2_data.INVALID_JSON, ProbeBatch, "ProbeBatch"
        )


def test_json_contract_does_not_allow_second_repair():
    provider = FakeLLMProvider(repair=m2_data.INVALID_JSON)
    with pytest.raises(SchemaContractError):
        load_validated_object(
            provider, "m", m2_data.INVALID_JSON, ProbeBatch, "ProbeBatch"
        )
    # Exactly ONE repair attempt -> exactly one provider call.
    assert len(provider.calls) == 1


def test_schema_contract_error_bubbles_to_orchestrator_human_review_required():
    # An unrecoverable tuning-stage schema error still bubbles to a fail-safe
    # HUMAN_REVIEW_REQUIRED. Here the Red Team also failed first and the loop
    # degraded to the deterministic baseline before the tuning agent broke its
    # contract — both failures are recorded and the baseline is preserved.
    provider = FakeLLMProvider(
        red=m2_data.INVALID_JSON,
        tuning=m2_data.INVALID_JSON,
        repair=m2_data.INVALID_JSON,
    )
    report = run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
    )
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    assert any("failed schema validation" in risk for risk in report.open_risks)
    assert report.human_review_requirements == ["schema_contract_failure"]
    # No dirty continuation: no patches applied.
    assert report.patch_operations_applied == []
    # Deterministic baseline is PRESERVED (no blank telemetry); both the Red Team
    # failure and the aborting tuning stage are recorded for the UI.
    assert report.before_results, "deterministic baseline must be preserved"
    assert report.metadata.red_team_status == "failed"
    assert report.metadata.failed_role == "tuning"
    assert report.metadata.failed_stage == "policy_tuning"


def test_parse_and_validate_helpers_directly():
    data = parse_json_object(m2_data.VALID_PROBE_BATCH)
    assert isinstance(data, dict)
    model = validate_model_object(data, ProbeBatch)
    assert isinstance(model, ProbeBatch)
