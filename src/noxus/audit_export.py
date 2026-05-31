"""Optional, local-only JSONL audit export for readiness reports.

This module writes newline-delimited JSON (one ReadinessReport per line) to a
LOCAL file when explicitly called. It makes no network calls, imports no cloud
SDKs, and runs nothing automatically. "Warehouse-ingestion compatible" here
means valid NDJSON with stable top-level fields — not any SDK integration.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from .schemas import ReadinessReport

# Bump this if the audit record's top-level shape changes.
AUDIT_SCHEMA_VERSION = "noxus-audit-1"


def report_to_audit_record(report: ReadinessReport) -> dict:
    """Build a stable, JSON-serializable audit record from a report.

    The full report is nested under ``report`` (serialized via Pydantic) and a
    handful of stable summary fields are promoted to the top level for easy
    downstream querying. Does not mutate the input report.
    """
    report_json = report.model_dump(mode="json")
    finding_count = sum(len(r.findings) for r in report.after_results)
    probe_count = len(report.probes_run) or len(report.before_results)
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "readiness_state": report.readiness_state.value,
        "before_score": report.before_score,
        "after_score": report.after_score,
        "probe_count": probe_count,
        "finding_count": finding_count,
        "open_risk_count": len(report.open_risks),
        "report": report_json,
    }


def append_audit_jsonl(
    report: ReadinessReport, output_path: Union[str, Path]
) -> Path:
    """Append one report as a JSON line to a local file. Returns the path.

    Creates parent directories if needed. Opens in append mode (never
    overwrites). UTF-8. No network, no cloud, no side effects beyond the file.
    """
    path = Path(output_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    record = report_to_audit_record(report)
    line = json.dumps(record, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path
