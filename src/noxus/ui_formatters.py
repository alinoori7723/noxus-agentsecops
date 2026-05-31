"""Pure-Python presentation helpers for the Noxus AgentSecOps demo UI.

This module is intentionally free of any view framework: it contains NO view-
library imports, type hints, hooks, or references whatsoever. It only transforms
accepted report objects (ReadinessReport, ProbeResult, Finding, PatchOperation)
into display-friendly plain dictionaries/lists, so it is fully unit-testable
without a browser.

Honest-labeling rules are enforced here, not in the view layer:
- deterministic_simulation -> "[DETERMINISTIC SIMULATION]"
- semantic_llm            -> "[SEMANTIC LLM JUDGMENT]"
- deterministic           -> "[DETERMINISTIC CHECK]"
"""

from __future__ import annotations

from .constants import SAFETY_RAIL_HEADING
from .schemas import (
    DetectionMode,
    PatchOp,
    ReadinessState,
)

# --------------------------------------------------------------------------- #
# Label / color maps (honest labels — never softened)
# --------------------------------------------------------------------------- #
_DETECTION_LABELS = {
    DetectionMode.deterministic_simulation.value: "[DETERMINISTIC SIMULATION]",
    DetectionMode.semantic_llm.value: "[SEMANTIC LLM JUDGMENT]",
    DetectionMode.deterministic.value: "[DETERMINISTIC CHECK]",
}

_READINESS_COLORS = {
    ReadinessState.PASS.value: "green",
    ReadinessState.CONDITIONAL_PASS.value: "amber",
    ReadinessState.HUMAN_REVIEW_REQUIRED.value: "red",
    ReadinessState.FAIL.value: "red",
}

# Substring that identifies the (intentionally) unresolved open risk.
_PROPRIETARY_RISK_KEY = "proprietary_context_exposure"


def _value(maybe_enum) -> str:
    """Return the .value of an enum, or the str of a plain value."""
    return getattr(maybe_enum, "value", None) or str(maybe_enum)


# --------------------------------------------------------------------------- #
# Atomic formatters
# --------------------------------------------------------------------------- #
def format_detection_label(detection_mode) -> str:
    """Map a detection mode to its honest, user-visible label."""
    key = _value(detection_mode)
    return _DETECTION_LABELS.get(key, f"[{key.upper()}]")


def format_readiness_badge(readiness_state) -> dict:
    """Return a display badge for a readiness state (no cosmetic promotion)."""
    key = _value(readiness_state)
    return {
        "state": key,
        "label": key,
        "color": _READINESS_COLORS.get(key, "red"),
        # CONDITIONAL_PASS is never silently shown as PASS.
        "is_pass": key == ReadinessState.PASS.value,
    }


def format_finding_row(finding) -> dict:
    """Flatten a Finding into a display row (confidence shown when present)."""
    confidence = getattr(finding, "confidence", None)
    return {
        "finding_type": finding.finding_type,
        "severity": _value(finding.severity),
        "detection_mode": _value(finding.detection_mode),
        "detection_label": format_detection_label(finding.detection_mode),
        "evidence": finding.evidence,
        "evidence_source": finding.evidence_source,
        "remediation_target": list(finding.remediation_target),
        "confidence": _value(confidence) if confidence is not None else None,
        "probe_id": finding.probe_id,
        "probe_type": _value(finding.probe_type),
    }


def format_probe_row(probe_result) -> dict:
    """Flatten a ProbeResult into a display row with its evidence snippets."""
    return {
        "probe_id": probe_result.probe_id,
        "probe_type": _value(probe_result.probe_type),
        "detection_mode": _value(probe_result.detection_mode),
        "detection_label": format_detection_label(probe_result.detection_mode),
        "passed": probe_result.passed,
        "status": "PASS" if probe_result.passed else "FAIL",
        "num_findings": len(probe_result.findings),
        "evidence": [f.evidence for f in probe_result.findings],
        "findings": [format_finding_row(f) for f in probe_result.findings],
    }


def format_patch_row(patch_operation) -> dict:
    """Flatten a PatchOperation into a display row."""
    detail = (
        patch_operation.clause_id
        or patch_operation.path
        or patch_operation.mask_type
        or patch_operation.block_type
        or patch_operation.category
        or ""
    )
    return {
        "operation": _value(patch_operation.operation),
        "target": patch_operation.target,
        "detail": detail,
        "source_finding": patch_operation.source_finding,
        "is_safety_rail": patch_operation.operation
        is PatchOp.insert_or_update_critical_safety_rail,
    }


def extract_safety_rail_preview(system_prompt: str) -> str:
    """Return the [CRITICAL_SAFETY_RAILS] section of a prompt, or "" if absent."""
    if not system_prompt or SAFETY_RAIL_HEADING not in system_prompt:
        return ""
    lines = system_prompt.splitlines()
    start = next(
        i for i, line in enumerate(lines) if line.strip() == SAFETY_RAIL_HEADING
    )
    preview: list[str] = []
    for line in lines[start:]:
        if line.strip() == "" and preview:
            break
        preview.append(line)
    return "\n".join(preview)


# --------------------------------------------------------------------------- #
# Composite models
# --------------------------------------------------------------------------- #
def _failed(results) -> int:
    return sum(1 for r in results if not r.passed)


def _finding_count(results) -> int:
    return sum(len(r.findings) for r in results)


def build_iteration_timeline(report) -> list[dict]:
    """Build a before/after timeline from real structured report data."""
    meta = report.metadata
    return [
        {
            "stage": "before",
            "label": "Before patching",
            "score": report.before_score,
            "total_probes": len(report.before_results),
            "failed_probes": _failed(report.before_results),
            "findings": _finding_count(report.before_results),
        },
        {
            "stage": "after",
            "label": "After patching",
            "score": report.after_score,
            "total_probes": len(report.after_results),
            "failed_probes": _failed(report.after_results),
            "findings": _finding_count(report.after_results),
            "score_delta": report.after_score - report.before_score,
            "readiness_state": _value(report.readiness_state),
            "mode": getattr(meta, "mode", "deterministic"),
            "tuning_iterations": getattr(meta, "tuning_iterations", 0),
        },
    ]


_NO_SAFETY_RAIL_PREVIEW = "No safety rail preview available from report data"


def _safety_rail_preview(report) -> str:
    """Derive the safety-rail preview from REAL execution data only.

    Priority order (per Milestone 3 data-integrity rule):
      A. the actual patched system prompt captured on the report
         (parsed via extract_safety_rail_preview);
      B. the actual clause text from the applied
         insert_or_update_critical_safety_rail patch operation;
      C. an honest empty/unknown state — NEVER a synthesized placeholder.
    """
    # A. Real patched system prompt telemetry.
    after_prompt = getattr(report, "after_system_prompt", None)
    if after_prompt:
        preview = extract_safety_rail_preview(after_prompt)
        if preview:
            return preview
    # B. Real applied safety-rail patch operation clause text.
    for op in report.patch_operations_applied:
        if (
            op.operation is PatchOp.insert_or_update_critical_safety_rail
            and op.content
        ):
            heading = op.heading or SAFETY_RAIL_HEADING
            clause_id = op.clause_id or ""
            return f"{heading}\n- ({clause_id}) {op.content}"
    # C. Honest empty/unknown state.
    return _NO_SAFETY_RAIL_PREVIEW


def build_red_blue_dashboard_model(report) -> dict:
    """Red side = probes/findings; Blue side = patches/safety rails."""
    patch_rows = [format_patch_row(op) for op in report.patch_operations_applied]
    red_probes = [format_probe_row(r) for r in report.after_results]
    red_findings = [
        format_finding_row(f) for r in report.after_results for f in r.findings
    ]
    return {
        "red": {
            "title": "Red Team — probes & findings",
            "probes": red_probes,
            "findings": red_findings,
            "failing_probes": [p for p in red_probes if not p["passed"]],
        },
        "blue": {
            "title": "Blue Team — patches & safety rails",
            "patches": patch_rows,
            "patch_engine_note": (
                "Patches are applied only by the deterministic patch engine; "
                "agents propose, they never apply."
            ),
            "safety_rail_preview": _safety_rail_preview(report),
        },
    }


def build_evidence_report_model(report) -> dict:
    """Surface findings, severities, labels, confidence, and open risks honestly."""
    findings = [
        format_finding_row(f) for r in report.after_results for f in r.findings
    ]
    open_risks = list(report.open_risks)
    proprietary_open = [r for r in open_risks if _PROPRIETARY_RISK_KEY in r]
    return {
        "readiness": format_readiness_badge(report.readiness_state),
        "findings": findings,
        "open_risks": open_risks,
        "human_review_requirements": list(report.human_review_requirements),
        # Honest flag: proprietary-context exposure is an UNRESOLVED open risk.
        "proprietary_context_exposure_unresolved": bool(proprietary_open),
        "proprietary_open_risks": proprietary_open,
        "before_score": report.before_score,
        "after_score": report.after_score,
    }
