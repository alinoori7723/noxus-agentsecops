from pathlib import Path

import pytest
from pydantic import ValidationError

from noxus.policy_loader import load_text_file, load_yaml_policy, validate_policy

SAMPLES = Path(__file__).resolve().parents[1] / "src" / "noxus" / "samples"


def test_load_text_file_reads_system_prompt():
    text = load_text_file(SAMPLES / "system_prompt.txt")
    assert "SupportBot" in text


def test_load_and_validate_sample_policy():
    raw = load_yaml_policy(SAMPLES / "security_policy.yaml")
    policy = validate_policy(raw)
    assert "api_key" in policy.sensitive_data.block
    assert policy.prompt_injection.detect_indirect_instructions is False


def test_validate_policy_rejects_unknown_field():
    with pytest.raises(ValidationError):
        validate_policy({"bogus": True})
