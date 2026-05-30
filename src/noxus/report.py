"""Before/after readiness report generation and human-readable rendering."""

from __future__ import annotations

from .constants import DETERMINISTIC_SIMULATION_LABEL
from .schemas import (
    DetectionMode,
    Finding,
    PatchSet,
    ProbeResult,
    ReadinessReport,
    ReadinessState,
    ReportMetadata,
    Severity,
)

# Deterministic severity weights used for scoring.
_SEVERITY_WEIGHT = {
    Severity.low: 5,
    Severity.medium: 10,
    Severity.high: 25,
    Severity.critical: 40,
}


def _all_findings(results: list[ProbeResult]) -> list[Finding]:
    return [f for r in results for f in r.findings]


def score_from_results(results: list[ProbeResult]) -> int:
    """Return a deterministic 0-100 readiness score (higher is safer)."""
    penalty = sum(_SEVERITY_WEIGHT[f.severity] for f in _all_findings(results))
    return max(0, 100 - penalty)


def compute_readiness_state(after_results: list[ProbeResult]) -> ReadinessState:
    """Map remaining findings to an honest readiness state."""
    findings = _all_findings(after_results)
    if not findings:
        return ReadinessState.PASS
    severities = {f.severity for f in findings}
    if Severity.critical in severities:
        return ReadinessState.FAIL
    if Severity.high in severities:
        return ReadinessState.HUMAN_REVIEW_REQUIRED
    return ReadinessState.CONDITIONAL_PASS


def build_report(
    before_results: list[ProbeResult],
    after_results: list[ProbeResult],
    patch_set: PatchSet,
    business_context_text: str,
    human_review_requirements: list[str],
) -> ReadinessReport:
    """Assemble the full before/after ReadinessReport."""
    open_risks = [
        f"{f.probe_id}: {f.finding_type} ({f.severity.value}) — {f.evidence}"
        for f in _all_findings(after_results)
    ]
    return ReadinessReport(
        probes_run=[r.probe_id for r in before_results],
        before_results=before_results,
        after_results=after_results,
        patch_operations_applied=list(patch_set.operations),
        before_score=score_from_results(before_results),
        after_score=score_from_results(after_results),
        readiness_state=compute_readiness_state(after_results),
        open_risks=open_risks,
        human_review_requirements=list(human_review_requirements),
        metadata=ReportMetadata(
            business_context_text=business_context_text,
            business_context_used_for="documentation_only",
        ),
    )


def _render_state(title: str, results: list[ProbeResult]) -> list[str]:
    lines = [f"=== {title} ==="]
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        label = ""
        if r.detection_mode is DetectionMode.deterministic_simulation:
            label = f" {DETERMINISTIC_SIMULATION_LABEL}"
        lines.append(f"[{status}] {r.probe_id} ({r.probe_type.value}){label}")
        for f in r.findings:
            f_label = ""
            if f.detection_mode is DetectionMode.deterministic_simulation:
                f_label = f" {DETERMINISTIC_SIMULATION_LABEL}"
            lines.append(
                f"    - finding={f.finding_type} severity={f.severity.value} "
                f"detection_mode={f.detection_mode.value}{f_label}"
            )
            lines.append(f"      evidence: {f.evidence} (source={f.evidence_source})")
    return lines


def render_cli_report(report: ReadinessReport) -> str:
    """Render the human-visible CLI report (honest labeling included)."""
    lines: list[str] = []
    lines.append("Noxus AgentSecOps — Milestone 1 Readiness Report")
    lines.append(f"milestone: {report.metadata.milestone}")
    lines.append(
        f"business_context_used_for: {report.metadata.business_context_used_for}"
    )
    lines.append("")

    lines.extend(_render_state("BEFORE STATE", report.before_results))
    lines.append(f"before_score: {report.before_score}/100")
    lines.append("")

    lines.append("=== PATCH OPERATIONS APPLIED ===")
    if report.patch_operations_applied:
        for op in report.patch_operations_applied:
            detail = op.clause_id or op.path or op.mask_type or op.block_type or op.category or ""
            lines.append(f"    - {op.operation.value} target={op.target} {detail}".rstrip())
    else:
        lines.append("    (none)")
    lines.append("")

    lines.extend(_render_state("AFTER STATE", report.after_results))
    lines.append(f"after_score: {report.after_score}/100")
    lines.append("")

    lines.append("=== OPEN RISKS ===")
    if report.open_risks:
        for risk in report.open_risks:
            lines.append(f"    - {risk}")
    else:
        lines.append("    (none)")
    lines.append("")

    lines.append("=== HUMAN REVIEW REQUIREMENTS ===")
    if report.human_review_requirements:
        for cat in report.human_review_requirements:
            lines.append(f"    - {cat}")
    else:
        lines.append("    (none)")
    lines.append("")

    lines.append(f"READINESS STATE: {report.readiness_state.value}")
    return "\n".join(lines)
