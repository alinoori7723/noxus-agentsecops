from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .schemas import ReadinessReport

AUDIT_SCHEMA_VERSION = "noxus-audit-1"


def report_to_audit_record(report: ReadinessReport) -> dict:

    report_json = report.model_dump(mode="json")
    finding_count = sum(len(r.findings) for r in report.after_results)
    probe_count = len(report.probes_run) or len(report.before_results)
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "exported_at_utc": datetime.now(UTC).isoformat(),
        "readiness_state": report.readiness_state.value,
        "before_score": report.before_score,
        "after_score": report.after_score,
        "probe_count": probe_count,
        "finding_count": finding_count,
        "open_risk_count": len(report.open_risks),
        "report": report_json,
    }


def append_audit_jsonl(report: ReadinessReport, output_path: str | Path) -> Path:

    path = Path(output_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    record = report_to_audit_record(report)
    line = json.dumps(record, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path
