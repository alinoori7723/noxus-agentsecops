from pathlib import Path

import m2_data
from noxus.cli import main
from noxus.llm_provider import FakeLLMProvider

SAMPLES = Path(__file__).resolve().parents[1] / "src" / "noxus" / "samples"
SP = str(SAMPLES / "system_prompt.txt")
POL = str(SAMPLES / "security_policy.yaml")
BC = str(SAMPLES / "business_context.md")


def test_cli_default_mode_is_deterministic(capsys):
    code = main(["run", "--system-prompt", SP, "--policy", POL, "--business-context", BC])
    out = capsys.readouterr().out
    assert code == 0
    assert "[DETERMINISTIC SIMULATION]" in out
    assert "READINESS STATE: CONDITIONAL_PASS" in out


def test_cli_agent_assisted_requires_env_vars(monkeypatch):
    monkeypatch.delenv("NOXUS_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("NOXUS_LLM_API_KEY", raising=False)
    code = main(
        [
            "run",
            "--mode",
            "agent-assisted",
            "--system-prompt",
            SP,
            "--policy",
            POL,
            "--business-context",
            BC,
        ]
    )
    assert code != 0


def test_cli_agent_assisted_uses_fake_or_mock_provider_in_tests(capsys):
    fake = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.EMPTY_PATCHSET,
    )
    code = main(
        [
            "run",
            "--mode",
            "agent-assisted",
            "--system-prompt",
            SP,
            "--policy",
            POL,
            "--business-context",
            BC,
        ],
        provider_factory=lambda: fake,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "READINESS STATE" in out
    assert len(fake.calls) > 0  # the fake provider really drove the run
