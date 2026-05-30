import pytest

import m2_data
from noxus.json_contracts import (
    SchemaContractError,
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
    # Red team output cannot be parsed/validated even after one repair.
    provider = FakeLLMProvider(red=m2_data.INVALID_JSON, repair=m2_data.INVALID_JSON)
    report = run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
    )
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    assert any("SchemaContractError" in risk for risk in report.open_risks)
    # No dirty continuation: no patches applied.
    assert report.patch_operations_applied == []


def test_parse_and_validate_helpers_directly():
    data = parse_json_object(m2_data.VALID_PROBE_BATCH)
    assert isinstance(data, dict)
    model = validate_model_object(data, ProbeBatch)
    assert isinstance(model, ProbeBatch)
