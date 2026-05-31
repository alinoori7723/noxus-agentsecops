import ast
import json
from pathlib import Path

import m2_data
from noxus.audit_export import (
    AUDIT_SCHEMA_VERSION,
    append_audit_jsonl,
    report_to_audit_record,
)
from noxus.orchestrator import run_readiness_assessment

_STABLE_TOP_LEVEL_FIELDS = {
    "schema_version",
    "exported_at_utc",
    "readiness_state",
    "before_score",
    "after_score",
    "probe_count",
    "finding_count",
    "open_risk_count",
    "report",
}


def _report():
    return run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="deterministic",
    )


def test_report_to_audit_record_has_stable_top_level_fields():
    record = report_to_audit_record(_report())
    assert _STABLE_TOP_LEVEL_FIELDS.issubset(record.keys())
    assert record["schema_version"] == AUDIT_SCHEMA_VERSION
    assert record["readiness_state"] == "CONDITIONAL_PASS"
    assert isinstance(record["before_score"], int)
    assert isinstance(record["after_score"], int)
    assert isinstance(record["report"], dict)
    # The whole record must be JSON-serializable.
    json.dumps(record)


def test_append_audit_jsonl_writes_one_valid_json_line(tmp_path):
    out = tmp_path / "audit" / "readiness_reports.jsonl"
    returned = append_audit_jsonl(_report(), out)
    assert returned == out
    assert out.exists()
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["schema_version"] == AUDIT_SCHEMA_VERSION


def test_append_audit_jsonl_appends_without_overwrite(tmp_path):
    out = tmp_path / "readiness_reports.jsonl"
    append_audit_jsonl(_report(), out)
    append_audit_jsonl(_report(), out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # both lines are valid JSON


def test_audit_export_does_not_mutate_report(tmp_path):
    report = _report()
    before = report.model_dump()
    append_audit_jsonl(report, tmp_path / "a.jsonl")
    report_to_audit_record(report)
    assert report.model_dump() == before


def test_audit_export_uses_local_files_only():
    # Static check: the module imports no network/cloud machinery.
    source = Path(__file__).resolve().parents[1] / "src" / "noxus" / "audit_export.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    network_or_cloud = {
        "urllib",
        "http",
        "socket",
        "ftplib",
        "requests",
        "httpx",
        "google",
        "boto3",
        "vertexai",
    }
    assert not (imported & network_or_cloud), f"unexpected imports: {imported}"
