import json
from pathlib import Path

import noxus.cli
from noxus.cli import main

SAMPLES = Path(__file__).resolve().parents[1] / "src" / "noxus" / "samples"
SP = str(SAMPLES / "system_prompt.txt")
POL = str(SAMPLES / "security_policy.yaml")
BC = str(SAMPLES / "business_context.md")


def _run_args(extra):
    return [
        "run",
        "--mode",
        "deterministic",
        "--system-prompt",
        SP,
        "--policy",
        POL,
        "--business-context",
        BC,
    ] + extra


def test_cli_audit_jsonl_output_writes_file_when_requested(tmp_path, capsys):
    out = tmp_path / "audit" / "readiness_reports.jsonl"
    code = main(_run_args(["--audit-jsonl-output", str(out)]))
    capsys.readouterr()
    assert code == 0
    assert out.exists()
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    json.loads(lines[0])


def test_cli_without_audit_jsonl_output_writes_no_file(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        noxus.cli, "append_audit_jsonl", lambda *a, **k: calls.append(a)
    )
    code = main(_run_args([]))
    capsys.readouterr()
    assert code == 0
    assert calls == []  # audit export never invoked without the flag
