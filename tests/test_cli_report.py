from pathlib import Path

from noxus.cli import main, run_pipeline
from noxus.constants import DETERMINISTIC_SIMULATION_LABEL
from noxus.report import render_cli_report
from noxus.schemas import ProbeType

SAMPLES = Path(__file__).resolve().parents[1] / "src" / "noxus" / "samples"
SYSTEM_PROMPT = str(SAMPLES / "system_prompt.txt")
POLICY = str(SAMPLES / "security_policy.yaml")
BUSINESS_CONTEXT = str(SAMPLES / "support_case_base.md")


def _report():
    return run_pipeline(SYSTEM_PROMPT, POLICY, BUSINESS_CONTEXT)


def _indirect(results):
    return next(r for r in results if r.probe_type is ProbeType.indirect_prompt_injection)


def test_cli_labels_indirect_injection_as_deterministic_simulation():
    rendered = render_cli_report(_report())
    assert DETERMINISTIC_SIMULATION_LABEL in rendered


def test_cli_smoke_run_prints_before_after_report(capsys):
    code = main(
        [
            "run",
            "--system-prompt",
            SYSTEM_PROMPT,
            "--policy",
            POLICY,
            "--business-context",
            BUSINESS_CONTEXT,
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "BEFORE STATE" in out
    assert "AFTER STATE" in out
    assert "READINESS STATE" in out
    assert DETERMINISTIC_SIMULATION_LABEL in out


def test_cli_smoke_run_exits_successfully():
    code = main(
        [
            "run",
            "--system-prompt",
            SYSTEM_PROMPT,
            "--policy",
            POLICY,
            "--business-context",
            BUSINESS_CONTEXT,
        ]
    )
    assert code == 0


def test_cli_after_state_passes_or_improves_indirect_injection_simulation():
    report = _report()
    before_indirect = _indirect(report.before_results)
    after_indirect = _indirect(report.after_results)
    # Before fails, after passes (and the overall score improves).
    assert before_indirect.passed is False
    assert after_indirect.passed is True
    assert report.after_score > report.before_score


def test_report_metadata_documentation_only_in_pipeline():
    report = _report()
    assert report.metadata.business_context_used_for == "documentation_only"
    assert "Acme Cloud" in report.metadata.business_context_text
