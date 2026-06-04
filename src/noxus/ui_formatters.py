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

from . import remediation
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

_READINESS_COPY = {
    ReadinessState.PASS.value: {
        "headline": "PASS — no open findings in retest",
        "explanation": (
            "The retest produced no remaining findings. Continue normal "
            "pre-production review before release."
        ),
    },
    ReadinessState.CONDITIONAL_PASS.value: {
        "headline": "CONDITIONAL_PASS — improved, but human review still required",
        "explanation": (
            "Noxus preserves unresolved proprietary-context exposure as an open "
            "risk rather than returning a fake PASS."
        ),
    },
    ReadinessState.HUMAN_REVIEW_REQUIRED.value: {
        "headline": "HUMAN_REVIEW_REQUIRED — reviewer action required",
        "explanation": (
            "The run reached a state that must be resolved by a human reviewer "
            "before production."
        ),
    },
    ReadinessState.FAIL.value: {
        "headline": "FAIL — critical findings remain",
        "explanation": (
            "Critical unresolved findings remain after retest. Do not treat "
            "this target as production-ready."
        ),
    },
}

_SEVERITY_COLORS = {
    "low": "green",
    "medium": "amber",
    "high": "red",
    "critical": "red",
}

_DETECTION_COLORS = {
    DetectionMode.deterministic_simulation.value: "amber",
    DetectionMode.semantic_llm.value: "blue",
    DetectionMode.deterministic.value: "green",
}

# Substring that identifies the (intentionally) unresolved open risk.
_PROPRIETARY_RISK_KEY = "proprietary_context_exposure"
_PROPRIETARY_RISK_EXPLANATION = (
    "This risk remains unresolved because Noxus does not auto-patch unsupported "
    "proprietary-context exposure. The correct result is CONDITIONAL_PASS, "
    "not fake PASS."
)


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
    copy = _READINESS_COPY.get(
        key,
        {
            "headline": key,
            "explanation": "Readiness state reported from the assessment result.",
        },
    )
    return {
        "state": key,
        "label": key,
        "color": _READINESS_COLORS.get(key, "red"),
        "headline": copy["headline"],
        "explanation": copy["explanation"],
        # CONDITIONAL_PASS is never silently shown as PASS.
        "is_pass": key == ReadinessState.PASS.value,
    }


def format_finding_row(finding) -> dict:
    """Flatten a Finding into a display row (confidence shown when present)."""
    confidence = getattr(finding, "confidence", None)
    severity = _value(finding.severity)
    detection_mode = _value(finding.detection_mode)
    remediation_target = list(finding.remediation_target)
    return {
        "finding_type": finding.finding_type,
        "severity": severity,
        "severity_color": _SEVERITY_COLORS.get(severity, "red"),
        "detection_mode": detection_mode,
        "detection_label": format_detection_label(finding.detection_mode),
        "detection_color": _DETECTION_COLORS.get(detection_mode, "red"),
        "evidence": finding.evidence,
        "evidence_source": finding.evidence_source,
        "remediation_target": remediation_target,
        "remediation_target_label": (
            ", ".join(remediation_target) if remediation_target else "not specified"
        ),
        "confidence": _value(confidence) if confidence is not None else None,
        "probe_id": finding.probe_id,
        "probe_type": _value(finding.probe_type),
    }


def format_probe_row(probe_result) -> dict:
    """Flatten a ProbeResult into a display row with its evidence snippets."""
    detection_mode = _value(probe_result.detection_mode)
    return {
        "probe_id": probe_result.probe_id,
        "probe_type": _value(probe_result.probe_type),
        "detection_mode": detection_mode,
        "detection_label": format_detection_label(probe_result.detection_mode),
        "detection_color": _DETECTION_COLORS.get(detection_mode, "red"),
        "passed": probe_result.passed,
        "status": "PASS" if probe_result.passed else "FAIL",
        "status_color": "green" if probe_result.passed else "red",
        "num_findings": len(probe_result.findings),
        "evidence": [f.evidence for f in probe_result.findings],
        "findings": [format_finding_row(f) for f in probe_result.findings],
    }


def format_patch_row(patch_operation, unresolved_finding_types=None) -> dict:
    """Flatten a PatchOperation into a display row with evidence lineage + status.

    ``source_label`` is NEVER empty for an applied patch (it cites finding ids /
    probe ids / finding types / source finding). ``status`` distinguishes a patch
    that was applied AND resolved its finding from one that was applied but the
    risk is still unresolved (or requires human review), or a rejected/unlinked
    proposal.
    """
    op = patch_operation
    detail = (
        op.clause_id
        or op.path
        or op.mask_type
        or op.block_type
        or op.category
        or ""
    )
    source_ids = list(op.source_finding_ids)
    source_probes = list(op.source_probe_ids)
    source_types = list(op.source_finding_types)
    label = remediation.patch_lineage_label(op)
    addressed = set(source_types) or ({op.source_finding} if op.source_finding else set())
    unresolved = set(unresolved_finding_types or [])
    if not source_ids and not source_probes and not source_types and not op.source_finding:
        status = "rejected_unlinked"
    elif op.operation is PatchOp.require_human_review_for_category:
        status = "applied_requires_human_review"
    elif addressed & unresolved:
        status = "applied_but_risk_unresolved"
    else:
        status = "applied_and_resolved"
    return {
        "operation": _value(op.operation),
        "target": op.target,
        "detail": detail,
        "source_finding": op.source_finding,
        "source_finding_ids": source_ids,
        "source_probe_ids": source_probes,
        "source_finding_types": source_types,
        "source_label": label,
        "status": status,
        "is_safety_rail": op.operation is PatchOp.insert_or_update_critical_safety_rail,
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


def summarize_probe_results(results) -> dict:
    """Summarize real probe-result counts for compact UI cards."""
    total = len(results)
    failed = _failed(results)
    findings = _finding_count(results)
    return {
        "total_probes": total,
        "passed_probes": total - failed,
        "failed_probes": failed,
        "findings": findings,
    }


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


def build_demo_timeline_model(report) -> list[dict]:
    """Build the six-step demo timeline from report fields only."""
    before = summarize_probe_results(report.before_results)
    after = summarize_probe_results(report.after_results)
    patch_count = len(report.patch_operations_applied)
    readiness = format_readiness_badge(report.readiness_state)
    score_delta = report.after_score - report.before_score
    safety_preview = _safety_rail_preview(report)
    has_safety_preview = SAFETY_RAIL_HEADING in safety_preview
    return [
        {
            "step": 1,
            "label": "Baseline probes",
            "status": "Complete" if before["total_probes"] else "No data",
            "status_color": "green" if before["total_probes"] else "amber",
            "description": (
                f"{before['total_probes']} probes ran against the original target."
            ),
            "evidence_count": before["findings"],
            "detail": f"{before['failed_probes']} failing probes before patching.",
        },
        {
            "step": 2,
            "label": "Findings",
            "status": "Needs patching" if before["findings"] else "Clear",
            "status_color": "red" if before["findings"] else "green",
            "description": "Evidence-backed findings captured before any patch.",
            "evidence_count": before["findings"],
            "detail": f"{before['findings']} baseline findings in the report.",
        },
        {
            "step": 3,
            "label": "Structured patch proposal",
            "status": "Proposed" if patch_count else "None",
            "status_color": "amber" if patch_count else "green",
            "description": "Patch operations are schema-bound report objects.",
            "evidence_count": patch_count,
            "detail": f"{patch_count} patch operations emitted by the run.",
        },
        {
            "step": 4,
            "label": "Deterministic patch application",
            "status": "Applied" if patch_count else "No changes",
            "status_color": "green" if patch_count else "amber",
            "description": "Only the deterministic patch engine applies changes.",
            "evidence_count": patch_count,
            "detail": (
                "Safety rail preview captured from telemetry."
                if has_safety_preview
                else "No safety rail preview available from report data."
            ),
        },
        {
            "step": 5,
            "label": "Retest",
            "status": "Improved" if score_delta > 0 else "Complete",
            "status_color": "green" if score_delta >= 0 else "red",
            "description": (
                f"{after['total_probes']} probes reran against the patched target."
            ),
            "evidence_count": after["findings"],
            "detail": f"{after['failed_probes']} failing probes after retest.",
        },
        {
            "step": 6,
            "label": "Final readiness",
            "status": readiness["state"],
            "status_color": readiness["color"],
            "description": readiness["headline"],
            "evidence_count": len(report.open_risks),
            "detail": (
                "Open risks remain visible."
                if report.open_risks
                else "No open risks in the report."
            ),
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


def build_remediation_model(report) -> dict:
    """Honest remediation-effectiveness view: resolved vs unresolved + telemetry.

    Distinguishes "patch applied" from "risk fixed". When patches were applied
    but blocking findings remain (after_score 0), it carries an explicit
    explanation so the UI never reads as a fake green success.
    """
    meta = report.metadata
    before_findings = [
        format_finding_row(f) for r in report.before_results for f in r.findings
    ]
    unresolved_findings = [
        format_finding_row(f) for r in report.after_results for f in r.findings
    ]
    before_types = {f["finding_type"] for f in before_findings}
    unresolved_types = {f["finding_type"] for f in unresolved_findings}
    resolved_types = sorted(before_types - unresolved_types)
    patch_count = len(report.patch_operations_applied)
    explanation = ""
    if patch_count and report.after_score == 0 and unresolved_findings:
        explanation = (
            "Patches were applied, but blocking findings remained in retest. "
            "Noxus refused to mark this target safe."
        )
    elif patch_count and unresolved_findings:
        explanation = (
            "Some patches resolved findings; unresolved findings still require "
            "human review."
        )
    return {
        "patch_application_count": patch_count,
        "patched_policy_effective": getattr(meta, "patched_policy_effective", False),
        "patched_system_prompt_effective": getattr(
            meta, "patched_system_prompt_effective", False
        ),
        "resolved_probe_count": getattr(meta, "resolved_probe_count", 0),
        "unresolved_probe_count": getattr(meta, "unresolved_probe_count", 0),
        "resolved_finding_count": getattr(meta, "resolved_finding_count", 0),
        "unresolved_finding_count": getattr(meta, "unresolved_finding_count", 0),
        "rejected_proposal_count": getattr(meta, "rejected_proposal_count", 0),
        "resolved_finding_types": resolved_types,
        "unresolved_findings": unresolved_findings,
        "human_review_categories": list(report.human_review_requirements),
        "after_score": report.after_score,
        "blocking_explanation": explanation,
    }


def build_red_blue_dashboard_model(report) -> dict:
    """Red side = probes/findings; Blue side = patches/safety rails.

    Blue-side patch rows carry evidence lineage + a resolved/unresolved status,
    plus rejected (unlinked) proposals that were NOT applied. Human-review
    categories are the deterministic, evidence-anchored list.
    """
    unresolved_finding_types = {
        f.finding_type for r in report.after_results for f in r.findings
    }
    patch_rows = [
        format_patch_row(op, unresolved_finding_types)
        for op in report.patch_operations_applied
    ]
    rejected_rows = [
        format_patch_row(op, unresolved_finding_types)
        for op in getattr(report, "rejected_patch_operations", [])
    ]
    baseline_probes = [format_probe_row(r) for r in report.before_results]
    red_probes = [format_probe_row(r) for r in report.after_results]
    red_findings = [
        format_finding_row(f) for r in report.after_results for f in r.findings
    ]
    remediation_model = build_remediation_model(report)
    return {
        "red": {
            "title": "Red Team — probes & findings",
            "baseline_probes": baseline_probes,
            "retest_probes": red_probes,
            "probes": red_probes,
            "findings": red_findings,
            "failing_probes": [p for p in red_probes if not p["passed"]],
            "before_summary": summarize_probe_results(report.before_results),
            "after_summary": summarize_probe_results(report.after_results),
        },
        "blue": {
            "title": "Blue Team — patches & safety rails",
            "patches": patch_rows,
            "rejected_proposals": rejected_rows,
            "patch_engine_note": (
                "Patches are applied only by the deterministic patch engine; "
                "agents propose, they never apply."
            ),
            "safety_rail_preview": _safety_rail_preview(report),
            "human_review_requirements": list(report.human_review_requirements),
            "open_risks": list(report.open_risks),
            "remediation": remediation_model,
            "resolved_finding_types": remediation_model["resolved_finding_types"],
            "unresolved_findings": remediation_model["unresolved_findings"],
            "blocking_explanation": remediation_model["blocking_explanation"],
        },
    }


def build_evidence_report_model(report) -> dict:
    """Surface findings, severities, labels, confidence, and open risks honestly."""
    before_findings = [
        format_finding_row(f) for r in report.before_results for f in r.findings
    ]
    findings = [
        format_finding_row(f) for r in report.after_results for f in r.findings
    ]
    open_risks = list(report.open_risks)
    proprietary_open = [r for r in open_risks if _PROPRIETARY_RISK_KEY in r]
    return {
        "readiness": format_readiness_badge(report.readiness_state),
        "before_findings": before_findings,
        "after_findings": findings,
        "findings": findings,
        "open_risks": open_risks,
        "human_review_requirements": list(report.human_review_requirements),
        # Honest flag: proprietary-context exposure is an UNRESOLVED open risk.
        "proprietary_context_exposure_unresolved": bool(proprietary_open),
        "proprietary_open_risks": proprietary_open,
        "proprietary_context_explanation": (
            _PROPRIETARY_RISK_EXPLANATION if proprietary_open else ""
        ),
        "before_score": report.before_score,
        "after_score": report.after_score,
    }


def build_readiness_summary_model(report) -> dict:
    """Return compact readiness metrics derived from the report."""
    before = summarize_probe_results(report.before_results)
    after = summarize_probe_results(report.after_results)
    evidence = build_evidence_report_model(report)
    return {
        "badge": format_readiness_badge(report.readiness_state),
        "before_score": report.before_score,
        "after_score": report.after_score,
        "score_delta": report.after_score - report.before_score,
        "before_summary": before,
        "after_summary": after,
        "open_risk_count": len(report.open_risks),
        "human_review_count": len(report.human_review_requirements),
        "proprietary_context_exposure_unresolved": evidence[
            "proprietary_context_exposure_unresolved"
        ],
        "proprietary_context_explanation": evidence[
            "proprietary_context_explanation"
        ],
        "mode": getattr(report.metadata, "mode", "deterministic"),
        "tuning_iterations": getattr(report.metadata, "tuning_iterations", 0),
    }


def build_engineering_safeguards_model() -> list[dict]:
    """Return concise trust-boundary proof points for the demo surface."""
    return [
        {
            "title": "Schema-bound outputs",
            "detail": (
                "Agent outputs validate against strict contracts before they can "
                "enter the workflow."
            ),
            "tone": "blue",
        },
        {
            "title": "Deterministic enforcement",
            "detail": (
                "The patch engine applies allowed changes; agents propose, they "
                "do not mutate prompts or policy directly."
            ),
            "tone": "green",
        },
        {
            "title": "AST scope guards",
            "detail": (
                "Static tests guard dependency boundaries and product-scope imports."
            ),
            "tone": "neutral",
        },
        {
            "title": "Non-root Docker runtime",
            "detail": "The packaged local demo runs as a non-root container user.",
            "tone": "neutral",
        },
        {
            "title": "Local-only JSONL export",
            "detail": "Audit export is opt-in, local, append-only newline JSON.",
            "tone": "amber",
        },
    ]
