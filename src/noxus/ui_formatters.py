from __future__ import annotations

from . import remediation
from .constants import SAFETY_RAIL_HEADING
from .schemas import (
    DetectionMode,
    PatchOp,
    ReadinessState,
)

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


_READINESS_GATE = {
    ReadinessState.PASS.value: "PASS",
    ReadinessState.CONDITIONAL_PASS.value: "CONDITIONAL",
    ReadinessState.HUMAN_REVIEW_REQUIRED.value: "BLOCKED",
    ReadinessState.FAIL.value: "BLOCKED",
}


def readiness_gate(readiness_state) -> str:

    return _READINESS_GATE.get(_value(readiness_state), "BLOCKED")


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
            "The run reached a state that must be resolved by a human reviewer before production."
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


READINESS_SCORE_EXPLANATION = (
    "Readiness score measures deployability. Higher is safer. Risk is "
    "represented separately by failed probes, unresolved findings, and "
    "human-review requirements."
)
BASELINE_READINESS_SCORE_LABEL = "Baseline readiness score"


_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_RANK_RISK_LEVEL = {0: "None", 1: "Low", 2: "Medium", 3: "High", 4: "Critical"}
_RISK_LEVEL_COLORS = {
    "Critical": "red",
    "High": "red",
    "Medium": "amber",
    "Low": "green",
    "None": "green",
}


_PROPRIETARY_RISK_KEY = "proprietary_context_exposure"
_PROPRIETARY_RISK_EXPLANATION = (
    "This risk remains unresolved because Noxus does not auto-patch unsupported "
    "proprietary-context exposure. The correct result is CONDITIONAL_PASS, "
    "not fake PASS."
)


def _value(maybe_enum) -> str:

    return getattr(maybe_enum, "value", None) or str(maybe_enum)


def risk_level_from_results(results) -> str:

    rank = 0
    for result in results:
        for finding in result.findings:
            rank = max(rank, _SEVERITY_RANK.get(_value(finding.severity), 0))
    return _RANK_RISK_LEVEL[rank]


def format_detection_label(detection_mode) -> str:

    key = _value(detection_mode)
    return _DETECTION_LABELS.get(key, f"[{key.upper()}]")


def format_readiness_badge(readiness_state) -> dict:

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
        "is_pass": key == ReadinessState.PASS.value,
    }


def format_finding_row(finding) -> dict:

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

    op = patch_operation
    detail = op.clause_id or op.path or op.mask_type or op.block_type or op.category or ""
    source_ids = list(op.source_finding_ids)
    source_probes = list(op.source_probe_ids)
    source_types = list(op.source_finding_types)

    primary_type = op.primary_source_finding_type
    primary_probe = op.primary_source_probe_id
    primary_id = f"{primary_probe}:{primary_type}" if primary_probe and primary_type else None
    primary_label = (
        primary_id if primary_id else (primary_type or remediation.patch_lineage_label(op))
    )

    related_groups = remediation.classify_related_findings(op)

    status = remediation.patch_status(op, unresolved_finding_types)
    return {
        "operation": _value(op.operation),
        "target": op.target,
        "detail": detail,
        "source_finding": op.source_finding,
        "source_finding_ids": source_ids,
        "source_probe_ids": source_probes,
        "source_finding_types": source_types,
        "primary_source_finding_type": primary_type,
        "primary_source_probe_id": primary_probe,
        "primary_source_finding_id": primary_id,
        "primary_source_label": primary_label,
        "secondary_source_finding_ids": list(op.secondary_source_finding_ids),
        "related_source_finding_ids": remediation.related_secondary_finding_ids(op),
        "related_finding_groups": related_groups,
        "source_label": remediation.patch_lineage_label(op),
        "status": status,
        "is_safety_rail": op.operation is PatchOp.insert_or_update_critical_safety_rail,
    }


def extract_safety_rail_preview(system_prompt: str) -> str:

    if not system_prompt or SAFETY_RAIL_HEADING not in system_prompt:
        return ""
    lines = system_prompt.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == SAFETY_RAIL_HEADING)
    preview: list[str] = []
    for line in lines[start:]:
        if line.strip() == "" and preview:
            break
        preview.append(line)
    return "\n".join(preview)


def _failed(results) -> int:
    return sum(1 for r in results if not r.passed)


def _finding_count(results) -> int:
    return sum(len(r.findings) for r in results)


def summarize_probe_results(results) -> dict:

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
            "description": (f"{before['total_probes']} probes ran against the original target."),
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
            "description": (f"{after['total_probes']} probes reran against the patched target."),
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

    after_prompt = getattr(report, "after_system_prompt", None)
    if after_prompt:
        preview = extract_safety_rail_preview(after_prompt)
        if preview:
            return preview

    for op in report.patch_operations_applied:
        if op.operation is PatchOp.insert_or_update_critical_safety_rail and op.content:
            heading = op.heading or SAFETY_RAIL_HEADING
            clause_id = op.clause_id or ""
            return f"{heading}\n- ({clause_id}) {op.content}"

    return _NO_SAFETY_RAIL_PREVIEW


def build_remediation_model(report) -> dict:

    meta = report.metadata
    before_findings = [format_finding_row(f) for r in report.before_results for f in r.findings]
    unresolved_findings = [format_finding_row(f) for r in report.after_results for f in r.findings]
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
            "Some patches resolved findings; unresolved findings still require human review."
        )
    resolved_finding_count = getattr(meta, "resolved_finding_count", 0)
    unresolved_finding_count = getattr(meta, "unresolved_finding_count", 0)

    after_score_explanation = ""
    if report.after_score == 0 and (resolved_finding_count or resolved_types):
        after_score_explanation = (
            "Readiness remains blocked because high-risk findings remain. "
            "Remediation progress is shown separately."
        )

    before_summary = summarize_probe_results(report.before_results)
    after_summary = summarize_probe_results(report.after_results)
    probe_finding_mapping = {
        "explanation": (
            "One probe may emit multiple findings, so probe counts and finding counts differ."
        ),
        "baseline_probe_count": before_summary["total_probes"],
        "baseline_failed_probe_count": before_summary["failed_probes"],
        "baseline_finding_count": before_summary["findings"],
        "retest_probe_count": after_summary["total_probes"],
        "retest_failed_probe_count": after_summary["failed_probes"],
        "retest_finding_count": after_summary["findings"],
        "resolved_finding_count": resolved_finding_count,
        "unresolved_finding_count": unresolved_finding_count,
        "baseline_finding_instance_count": before_summary["findings"],
        "retest_finding_instance_count": after_summary["findings"],
        "resolved_finding_instance_count": resolved_finding_count,
        "unresolved_finding_instance_count": after_summary["findings"],
        "unresolved_finding_types": sorted(unresolved_types),
        "baseline_label": (
            f"{before_summary['failed_probes']} failed probes -> "
            f"{before_summary['findings']} finding instances"
        ),
        "retest_label": (
            f"{after_summary['failed_probes']} failed probes -> "
            f"{after_summary['findings']} unresolved finding instances"
        ),
        "resolved_label": f"{resolved_finding_count} finding instances resolved",
        "note": (
            "One probe may emit multiple findings. Remediation progress is "
            "counted by finding instances; human review is grouped by unresolved "
            "finding categories."
        ),
    }

    gate = readiness_gate(report.readiness_state)
    score_delta = report.after_score - report.before_score
    is_pass = report.readiness_state is ReadinessState.PASS
    gate_blocking_finding_types = sorted(unresolved_types)
    gate_blocked_explanation = ""
    gate_blocking_reason = ""
    if not is_pass:
        reason_items = gate_blocking_finding_types or list(report.human_review_requirements)
        if reason_items:
            gate_blocking_reason = "Reason: " + ", ".join(reason_items) + " unresolved"
        if score_delta > 0:
            gate_blocked_explanation = (
                "Readiness improved, but deployment remains blocked because "
                "unresolved high-risk findings remain."
            )

    routing = remediation.route_unresolved_instances(
        report.after_results, list(report.human_review_requirements)
    )
    human_review_derivation = routing["human_review_derivation"]
    return {
        "patch_application_count": patch_count,
        "patched_policy_effective": getattr(meta, "patched_policy_effective", False),
        "patched_system_prompt_effective": getattr(meta, "patched_system_prompt_effective", False),
        "resolved_probe_count": getattr(meta, "resolved_probe_count", 0),
        "unresolved_probe_count": getattr(meta, "unresolved_probe_count", 0),
        "resolved_finding_count": resolved_finding_count,
        "unresolved_finding_count": getattr(meta, "unresolved_finding_count", 0),
        "rejected_proposal_count": getattr(meta, "rejected_proposal_count", 0),
        "resolved_finding_types": resolved_types,
        "resolved_primary_finding_types": resolved_types,
        "unresolved_finding_types": sorted(unresolved_types),
        "unresolved_findings": unresolved_findings,
        "human_review_categories": list(report.human_review_requirements),
        "human_review_derivation": human_review_derivation,
        "unresolved_finding_instances": routing["unresolved_finding_instances"],
        "unresolved_not_human_reviewed": routing["unresolved_not_human_reviewed"],
        "human_review_derived_finding_instance_count": routing[
            "human_review_derived_finding_instance_count"
        ],
        "human_review_derived_finding_type_count": routing[
            "human_review_derived_finding_type_count"
        ],
        "remediation_progress": {
            "resolved": resolved_finding_count,
            "unresolved": getattr(meta, "unresolved_finding_count", 0),
            "label": (
                f"{resolved_finding_count} resolved / "
                f"{getattr(meta, 'unresolved_finding_count', 0)} unresolved"
            ),
        },
        "readiness_gate": gate,
        "readiness_gate_score": report.after_score,
        "after_score": report.after_score,
        "after_score_label": "Readiness gate score",
        "after_score_explanation": after_score_explanation,
        "blocking_explanation": explanation,
        "probe_finding_mapping": probe_finding_mapping,
        "gate_blocked_explanation": gate_blocked_explanation,
        "gate_blocking_reason": gate_blocking_reason,
        "gate_blocking_finding_types": gate_blocking_finding_types,
    }


_REPORT_SUMMARY_COPY = (
    "Noxus did not mark this target safe. It resolved supported findings, "
    "preserved unresolved risks, and routed the remaining categories to human "
    "review."
)


def build_report_summary_model(report) -> dict:

    meta = report.metadata
    before_types = {f.finding_type for r in report.before_results for f in r.findings}
    unresolved_types = sorted({f.finding_type for r in report.after_results for f in r.findings})
    resolved_types = sorted(before_types - set(unresolved_types))
    resolved_finding_count = getattr(meta, "resolved_finding_count", 0)
    human_review_categories = list(report.human_review_requirements)
    is_pass = report.readiness_state is ReadinessState.PASS
    why_not_pass = ""
    if not is_pass:
        why_not_pass = (
            "Final state is not PASS because unsupported or unresolved high-risk "
            "findings remain after retest."
        )
    return {
        "readiness_gate": readiness_gate(report.readiness_state),
        "is_pass": is_pass,
        "what_improved": {
            "resolved_finding_count": resolved_finding_count,
            "resolved_finding_types": resolved_types,
            "primary_finding_types_resolved": resolved_types,
        },
        "what_remains_blocked": {
            "unresolved_finding_types": unresolved_types,
            "human_review_categories": human_review_categories,
        },
        "gate_blocking_finding_types": unresolved_types,
        "why_not_pass": why_not_pass,
        "summary_copy": "" if is_pass else _REPORT_SUMMARY_COPY,
    }


def build_red_blue_dashboard_model(report) -> dict:

    unresolved_finding_types = {f.finding_type for r in report.after_results for f in r.findings}
    patch_rows = [
        format_patch_row(op, unresolved_finding_types) for op in report.patch_operations_applied
    ]
    rejected_rows = [
        format_patch_row(op, unresolved_finding_types)
        for op in getattr(report, "rejected_patch_operations", [])
    ]
    baseline_probes = [format_probe_row(r) for r in report.before_results]
    red_probes = [format_probe_row(r) for r in report.after_results]
    red_findings = [format_finding_row(f) for r in report.after_results for f in r.findings]
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
            "human_review_derivation": remediation_model["human_review_derivation"],
            "open_risks": list(report.open_risks),
            "remediation": remediation_model,
            "resolved_finding_types": remediation_model["resolved_finding_types"],
            "unresolved_findings": remediation_model["unresolved_findings"],
            "blocking_explanation": remediation_model["blocking_explanation"],
        },
    }


def build_evidence_report_model(report) -> dict:

    before_findings = [format_finding_row(f) for r in report.before_results for f in r.findings]
    findings = [format_finding_row(f) for r in report.after_results for f in r.findings]
    open_risks = list(report.open_risks)
    proprietary_open = [r for r in open_risks if _PROPRIETARY_RISK_KEY in r]
    return {
        "readiness": format_readiness_badge(report.readiness_state),
        "before_findings": before_findings,
        "after_findings": findings,
        "findings": findings,
        "open_risks": open_risks,
        "human_review_requirements": list(report.human_review_requirements),
        "proprietary_context_exposure_unresolved": bool(proprietary_open),
        "proprietary_open_risks": proprietary_open,
        "proprietary_context_explanation": (
            _PROPRIETARY_RISK_EXPLANATION if proprietary_open else ""
        ),
        "before_score": report.before_score,
        "after_score": report.after_score,
    }


def build_readiness_summary_model(report) -> dict:

    before = summarize_probe_results(report.before_results)
    after = summarize_probe_results(report.after_results)
    evidence = build_evidence_report_model(report)
    meta = report.metadata
    resolved_finding_count = getattr(meta, "resolved_finding_count", 0)
    unresolved_finding_count = getattr(meta, "unresolved_finding_count", 0)
    after_score_explanation = ""
    if report.after_score == 0 and resolved_finding_count:
        after_score_explanation = (
            "Readiness remains blocked because high-risk findings remain. "
            "Remediation progress is shown separately."
        )

    risk_level = risk_level_from_results(report.after_results)
    gate = readiness_gate(report.readiness_state)
    score_delta = report.after_score - report.before_score
    is_pass = report.readiness_state is ReadinessState.PASS

    gate_blocked_explanation = ""
    if not is_pass and score_delta > 0:
        gate_blocked_explanation = (
            "Readiness improved, but deployment remains blocked because "
            "unresolved high-risk findings remain."
        )
    return {
        "badge": format_readiness_badge(report.readiness_state),
        "readiness_gate": gate,
        "before_score": report.before_score,
        "before_score_label": BASELINE_READINESS_SCORE_LABEL,
        "baseline_readiness_score_label": BASELINE_READINESS_SCORE_LABEL,
        "readiness_gate_score_label": "Readiness gate score",
        "score_direction_explanation": READINESS_SCORE_EXPLANATION,
        "qualitative_risk_level": risk_level,
        "after_score": report.after_score,
        "after_score_label": "Readiness gate score",
        "after_score_explanation": after_score_explanation,
        "readiness_score_explanation": READINESS_SCORE_EXPLANATION,
        "risk_level": risk_level,
        "risk_level_label": "Risk remaining",
        "risk_color": _RISK_LEVEL_COLORS.get(risk_level, "red"),
        "gate_blocked_explanation": gate_blocked_explanation,
        "remediation_progress": {
            "resolved": resolved_finding_count,
            "unresolved": unresolved_finding_count,
            "label": f"{resolved_finding_count} resolved / {unresolved_finding_count} unresolved",
        },
        "score_delta": report.after_score - report.before_score,
        "before_summary": before,
        "after_summary": after,
        "open_risk_count": len(report.open_risks),
        "human_review_count": len(report.human_review_requirements),
        "proprietary_context_exposure_unresolved": evidence[
            "proprietary_context_exposure_unresolved"
        ],
        "proprietary_context_explanation": evidence["proprietary_context_explanation"],
        "mode": getattr(report.metadata, "mode", "deterministic"),
        "tuning_iterations": getattr(report.metadata, "tuning_iterations", 0),
    }


def build_engineering_safeguards_model() -> list[dict]:

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
            "detail": ("Static tests guard dependency boundaries and product-scope imports."),
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
