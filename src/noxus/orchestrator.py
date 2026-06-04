"""Orchestration layer for deterministic and agent-assisted readiness runs.

The deterministic mode preserves Milestone 1 behavior exactly. The
agent-assisted mode layers schema-bound LLM agents on top, but the deterministic
patch engine remains the ONLY component allowed to apply patches, and the
deterministic evaluator is always run (agents supplement, never replace it).

Any SchemaContractError raised by an agent or by json_contracts is caught here:
further LLM execution stops immediately, no patch is applied, and a clean
ReadinessReport with readiness_state = HUMAN_REVIEW_REQUIRED is returned.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import ValidationError

from .agents import (
    PolicyTuningAgent,
    RedTeamAgent,
    SemanticJudgeAgent,
    SEMANTIC_JUDGE_PROBE_TYPES,
)
from .constants import MAX_TUNING_ITERATIONS
from .evaluator import DeterministicEvaluator
from .errors import SchemaContractError
from .json_contracts import sanitize_excerpt
from .llm_provider import LLMProvider
from .patch_engine import apply_patch_set
from .patch_mapper import generate_patches_from_findings
from .policy_loader import validate_policy
from .remediation import attach_patch_lineage
from .probe_registry import get_probes
from .report import build_report, score_from_results
from .schemas import (
    Confidence,
    DetectionMode,
    Finding,
    PatchSet,
    Probe,
    ProbeResult,
    ReadinessReport,
    ReadinessState,
    ReportMetadata,
    SecurityPolicy,
    Severity,
)

Mode = Literal["deterministic", "agent_assisted"]

_CONFIDENCE_SEVERITY = {
    Confidence.low: Severity.low,
    Confidence.medium: Severity.medium,
    Confidence.high: Severity.high,
}


def _as_policy(policy: Any) -> SecurityPolicy:
    if isinstance(policy, SecurityPolicy):
        return policy
    return validate_policy(policy)


def run_readiness_assessment(
    *,
    system_prompt: str,
    policy: Any,
    business_context_text: str,
    mode: Mode = "deterministic",
    provider: Optional[LLMProvider] = None,
    red_model: str = "gemini-3.5-flash",
    judge_model: str = "gemini-3.5-flash",
    tuning_model: str = "gemini-3.1-pro-preview",
) -> ReadinessReport:
    """Run a readiness assessment in the requested mode."""
    if mode == "deterministic":
        return _run_deterministic(system_prompt, policy, business_context_text)
    if mode == "agent_assisted":
        if provider is None:
            raise ValueError("agent_assisted mode requires an LLM provider.")
        return _run_agent_assisted(
            system_prompt,
            policy,
            business_context_text,
            provider,
            red_model,
            judge_model,
            tuning_model,
        )
    raise ValueError(f"Unknown mode: {mode!r}")


# --------------------------------------------------------------------------- #
# Deterministic mode (Milestone 1 behavior, unchanged)
# --------------------------------------------------------------------------- #
def _run_deterministic(
    system_prompt: str, policy: Any, business_context_text: str
) -> ReadinessReport:
    sp = _as_policy(policy)
    probes = get_probes()
    evaluator = DeterministicEvaluator()

    before_results = evaluator.evaluate(probes, system_prompt, sp)
    before_findings = [f for r in before_results for f in r.findings]

    patch_set = generate_patches_from_findings(before_findings)
    # Attach evidence lineage; only lineage-linked patches are applied (the
    # deterministic mapper only emits finding-anchored patches, so all link).
    linked, unlinked = attach_patch_lineage(patch_set.operations, before_findings)
    patch_set = PatchSet(operations=linked)
    patched_prompt, patched_policy_dict = apply_patch_set(
        system_prompt, sp.model_dump(), patch_set
    )
    patched_policy = validate_policy(patched_policy_dict)

    after_results = evaluator.evaluate(probes, patched_prompt, patched_policy)

    report = build_report(
        before_results=before_results,
        after_results=after_results,
        patch_set=patch_set,
        business_context_text=business_context_text,
        human_review_requirements=patched_policy.human_review.required_categories,
    )
    # Presentation telemetry only: expose the REAL patched system prompt so the
    # UI can render an honest safety-rail preview (no scoring/state impact).
    report.after_system_prompt = patched_prompt
    report.metadata.evidence_basis = "deterministic_baseline"
    _stamp_remediation_effectiveness(
        report,
        original_prompt=system_prompt,
        current_prompt=patched_prompt,
        original_policy=sp,
        current_policy=patched_policy,
        applied_ops=list(patch_set.operations),
        rejected_ops=unlinked,
    )
    return report


# --------------------------------------------------------------------------- #
# Agent-assisted mode
# --------------------------------------------------------------------------- #
def _semantic_finding(probe: Probe, judgment) -> Finding:
    return Finding(
        finding_type=judgment.suggested_finding_type
        or f"{probe.probe_type.value}_semantic",
        severity=_CONFIDENCE_SEVERITY[judgment.confidence],
        detection_mode=DetectionMode.semantic_llm,
        probe_id=probe.probe_id,
        probe_type=probe.probe_type,
        description=f"Semantic judge: {judgment.reason}",
        evidence=judgment.reason[:160],
        evidence_source="semantic_llm_judgment",
        remediation_target=["system_prompt", "security_policy"],
        confidence=judgment.confidence,
    )


def _apply_semantic_judge(
    judge: SemanticJudgeAgent,
    probes: list[Probe],
    results: list[ProbeResult],
    policy: SecurityPolicy,
    system_prompt: str,
) -> list[ProbeResult]:
    """Supplement (never replace) deterministic findings with semantic ones."""
    merged: list[ProbeResult] = []
    for probe, result in zip(probes, results):
        if probe.probe_type not in SEMANTIC_JUDGE_PROBE_TYPES:
            merged.append(result)
            continue
        judgment = judge.judge(
            probe, result.target_response, result.findings, policy, system_prompt
        )
        if not judgment.semantic_violation:
            merged.append(result)
            continue
        # Deterministic findings are preserved; semantic finding is appended.
        new_findings = list(result.findings) + [_semantic_finding(probe, judgment)]
        merged.append(
            ProbeResult(
                probe_id=result.probe_id,
                probe_type=result.probe_type,
                detection_mode=result.detection_mode,
                passed=len(new_findings) == 0,
                target_response=result.target_response,
                findings=new_findings,
            )
        )
    return merged


# Maps the failing orchestration stage to the responsible agent role. A failure
# while APPLYING a patch is attributed to the tuning agent that proposed it.
_STAGE_ROLE = {
    "red_team_generation": "red",
    "semantic_judge": "judge",
    "policy_tuning": "tuning",
    "patch_application": "tuning",
}


def _stamp_remediation_effectiveness(
    report: ReadinessReport,
    *,
    original_prompt: str,
    current_prompt: str,
    original_policy: SecurityPolicy,
    current_policy: SecurityPolicy,
    applied_ops: list,
    rejected_ops: list,
) -> None:
    """Stamp remediation-effectiveness telemetry + rejected-proposal lineage.

    Verifies the retest target actually differs from the original (the loop
    always retests against ``current_*``), and records unlinked proposals as
    rejected — never applied, never counted as remediation. Presentation/audit
    only; no scoring/readiness impact.
    """
    report.metadata.patched_system_prompt_effective = current_prompt != original_prompt
    report.metadata.patched_policy_effective = (
        current_policy.model_dump() != original_policy.model_dump()
    )
    report.metadata.patch_application_count = len(applied_ops)
    report.metadata.rejected_proposal_count = len(rejected_ops)
    report.rejected_patch_operations = list(rejected_ops)


def _stamp_red_fallback(metadata: ReportMetadata, ctx: Optional[dict]) -> None:
    """Stamp Red-Team resilience telemetry onto report metadata (presentation only).

    ``ctx`` is the small context dict assembled by the orchestrator when the Red
    Team Agent failed. It records, honestly, that the Red Team failed and (if
    applicable) that the loop continued on deterministic baseline evidence. It
    never affects scoring or readiness.
    """
    if not ctx:
        return
    metadata.red_team_status = ctx.get("red_team_status")
    metadata.fallback_used = ctx.get("fallback_used")
    metadata.fallback_reason = ctx.get("fallback_reason")
    metadata.continued_after_red_failure = bool(ctx.get("continued_after_red_failure"))
    metadata.red_team_failure_excerpt = ctx.get("red_team_failure_excerpt")


def _human_review_report(
    stage: str,
    error: Exception,
    before_results: Optional[list[ProbeResult]],
    business_context_text: str,
    fallback_ctx: Optional[dict] = None,
) -> ReadinessReport:
    """Build a HUMAN_REVIEW_REQUIRED report that PRESERVES the deterministic baseline.

    When the deterministic baseline already ran, its probes/findings/evidence are
    kept in the report so the UI shows partial evidence instead of a blank state.
    The failed stage, role, and a sanitized output excerpt are recorded as
    presentation-only metadata. ``fallback_ctx`` (when present) additionally
    records that the Red Team Agent failed earlier and the loop continued on
    deterministic baseline evidence before THIS stage failed — so a report can
    honestly show BOTH failed stages with the baseline preserved.
    """
    before = before_results or []
    # Sanitize the error text (redact secrets, cap length) before it reaches any
    # user-visible surface — it may quote LLM-proposed patch content.
    safe_error = sanitize_excerpt(str(error))
    open_risks = [
        f"Agent-assisted stage '{stage}' failed schema validation: {safe_error}. "
        "LLM execution aborted; no patches applied. The deterministic baseline "
        "below is preserved."
    ]
    # Preserve every deterministic baseline finding as an explicit open risk so it
    # stays visible (e.g. proprietary-context exposure) even on a partial run.
    for r in before:
        for f in r.findings:
            open_risks.append(
                f"{f.probe_id}: {f.finding_type} ({f.severity.value}) — {f.evidence}"
            )
    # SchemaContractError carries a pre-sanitized excerpt; for any other error
    # (e.g. a Pydantic ValidationError from a bad LLM patch) sanitize its text.
    excerpt = getattr(error, "raw_excerpt", None) or safe_error
    metadata = ReportMetadata(
        business_context_text=business_context_text,
        mode="agent_assisted",
        tuning_iterations=0,
        failed_stage=stage,
        failed_role=_STAGE_ROLE.get(stage),
        schema_failure_excerpt=excerpt,
    )
    _stamp_red_fallback(metadata, fallback_ctx)
    return ReadinessReport(
        probes_run=[r.probe_id for r in before],
        before_results=before,
        after_results=[],
        patch_operations_applied=[],
        before_score=score_from_results(before) if before else 0,
        after_score=0,
        readiness_state=ReadinessState.HUMAN_REVIEW_REQUIRED,
        open_risks=open_risks,
        human_review_requirements=["schema_contract_failure"],
        metadata=metadata,
    )


def _run_agent_assisted(
    system_prompt: str,
    policy: Any,
    business_context_text: str,
    provider: LLMProvider,
    red_model: str,
    judge_model: str,
    tuning_model: str,
) -> ReadinessReport:
    # Validate the INPUT policy outside the fail-safe try: a malformed input
    # policy is a caller error, not an LLM-caused failure, and must propagate
    # rather than be masked as a schema-contract failure (mirrors deterministic
    # mode). The ValidationError catch below is reserved for LLM patch effects.
    sp = _as_policy(policy)

    evaluator = DeterministicEvaluator()
    judge = SemanticJudgeAgent(provider, judge_model)
    tuner = PolicyTuningAgent(provider, tuning_model)

    current_prompt = system_prompt
    current_policy = sp

    # 1. DETERMINISTIC BASELINE FIRST — always runs, never depends on the LLM.
    # Stored immediately so a later agent failure still yields a report with real
    # baseline probes/findings/evidence (no blank telemetry).
    baseline_probes = get_probes()
    baseline_results = evaluator.evaluate(baseline_probes, current_prompt, current_policy)
    baseline_findings = [f for r in baseline_results for f in r.findings]

    # Red-Team resilience context (presentation-only). Always record that the Red
    # Team ran ("used"); flip to "failed" + fallback if it breaks the contract.
    red_team_status = "used"
    fallback_ctx: Optional[dict] = None
    continued_after_red_failure = False
    before_results: list[ProbeResult] = baseline_results

    # 2. Try the Red Team Agent. A Red Team schema failure must NOT kill the loop
    # when the deterministic baseline already produced findings — it DEGRADES to
    # the deterministic baseline as the fallback evidence source. We never
    # fabricate Red Team probes.
    probes = baseline_probes
    try:
        red = RedTeamAgent(provider, red_model)
        agent_probes = red.generate_probes(system_prompt, sp, business_context_text)
        probes = baseline_probes + agent_probes
    except (SchemaContractError, ValidationError) as red_exc:
        red_team_status = "failed"
        red_excerpt = getattr(red_exc, "raw_excerpt", None) or sanitize_excerpt(
            str(red_exc)
        )
        if not baseline_findings:
            # Nothing to fall back to — honest HUMAN_REVIEW_REQUIRED for the red
            # stage (baseline still preserved, just no findings to remediate).
            report = _human_review_report(
                "red_team_generation",
                red_exc,
                baseline_results,
                business_context_text,
                fallback_ctx={
                    "red_team_status": "failed",
                    "fallback_used": None,
                    "fallback_reason": "red_team_schema_contract_failure",
                    "continued_after_red_failure": False,
                    "red_team_failure_excerpt": red_excerpt,
                },
            )
            # Only the deterministic baseline ran; the judge never executed.
            report.metadata.evidence_basis = "deterministic_baseline"
            return report
        # Degrade: continue using the deterministic baseline probes/findings.
        continued_after_red_failure = True
        probes = baseline_probes
        fallback_ctx = {
            "red_team_status": "failed",
            "fallback_used": "deterministic_baseline",
            "fallback_reason": "red_team_schema_contract_failure",
            "continued_after_red_failure": True,
            "red_team_failure_excerpt": red_excerpt,
        }

    # Context stamped onto every report from here on (success OR later failure).
    if fallback_ctx is None and red_team_status == "used":
        report_ctx = None
    else:
        report_ctx = fallback_ctx

    # Evidence basis + semantic-judge resilience (presentation-only; symmetric
    # with the Red-Team fallback). The judge SUPPLEMENTS deterministic findings;
    # if it breaks its schema contract the loop DEGRADES (drops the unusable
    # semantic supplement, keeps deterministic + valid red-team evidence,
    # continues to tuning) instead of aborting. It never fabricates findings.
    if continued_after_red_failure:
        evidence_basis = "degraded_fallback"
        semantic_judge_status: Optional[str] = "skipped"
    else:
        evidence_basis = "red_team_augmented"
        semantic_judge_status = "used"
    judge_failed = False
    judge_excerpt: Optional[str] = None

    def _maybe_apply_judge(results_in: list[ProbeResult]) -> list[ProbeResult]:
        nonlocal judge_failed, judge_excerpt, semantic_judge_status
        # Skip when the run already degraded (red fallback) or the judge has
        # already failed once this run — never retry a broken contract.
        if continued_after_red_failure or judge_failed:
            return results_in
        try:
            return _apply_semantic_judge(
                judge, probes, results_in, current_policy, current_prompt
            )
        except (SchemaContractError, ValidationError) as exc:
            # DEGRADE: drop the (unusable) semantic supplement, keep the
            # deterministic + valid red-team evidence, and continue to tuning.
            judge_failed = True
            semantic_judge_status = "failed"
            judge_excerpt = getattr(exc, "raw_excerpt", None) or sanitize_excerpt(
                str(exc)
            )
            return results_in

    def _stamp(report: ReadinessReport) -> ReadinessReport:
        report.metadata.semantic_judge_status = semantic_judge_status
        report.metadata.semantic_judge_failure_excerpt = judge_excerpt
        report.metadata.evidence_basis = evidence_basis
        return report

    # From here, an unrecoverable TUNING/PATCH schema failure routes to
    # HUMAN_REVIEW_REQUIRED with the baseline preserved AND the prior-stage trace
    # recorded. A judge failure no longer aborts (it degrades, see above).
    stage = "policy_tuning"
    try:
        # 3. Evaluate the probe set (full set on red success; baseline on fallback).
        results = evaluator.evaluate(probes, current_prompt, current_policy)

        # 4. Semantic judge — supplement (skipped on red fallback; degrades on
        # its own schema failure).
        results = _maybe_apply_judge(results)
        before_results = results

        applied_ops = []
        rejected_ops = []
        iterations_done = 0
        # 5-7 / 12. Policy tuning bounded by MAX_TUNING_ITERATIONS. In fallback
        # mode this proposes patches from the deterministic baseline findings.
        while iterations_done < MAX_TUNING_ITERATIONS:
            findings = [f for r in results for f in r.findings]
            if not findings:
                break
            # 8-9. Propose + validate PatchSet (agent never applies patches).
            stage = "policy_tuning"
            patch_set = tuner.propose_patches(findings, current_policy, current_prompt)
            # 8b. Evidence lineage: bind each proposed op to the finding(s) it
            # addresses. Ops with no safe lineage are NOT applied — they are
            # recorded as rejected/unlinked proposals (never counted as
            # remediation), so the LLM cannot smuggle an unmotivated edit.
            linked, unlinked = attach_patch_lineage(patch_set.operations, findings)
            rejected_ops.extend(unlinked)
            # 10. Deterministic patch engine is the ONLY applier; only linked ops.
            stage = "patch_application"
            new_prompt, new_policy_dict = apply_patch_set(
                current_prompt, current_policy.model_dump(), PatchSet(operations=linked)
            )
            current_prompt = new_prompt
            current_policy = validate_policy(new_policy_dict)
            applied_ops.extend(linked)
            iterations_done += 1
            # 11. Rerun probes (+ semantic supplement, unless skipped/degraded).
            results = evaluator.evaluate(probes, current_prompt, current_policy)
            results = _maybe_apply_judge(results)

        after_results = results
        report = build_report(
            before_results=before_results,
            after_results=after_results,
            patch_set=PatchSet(operations=applied_ops),
            business_context_text=business_context_text,
            human_review_requirements=current_policy.human_review.required_categories,
        )
        report.metadata.mode = "agent_assisted"
        report.metadata.tuning_iterations = iterations_done
        report.metadata.red_team_status = red_team_status
        _stamp_red_fallback(report.metadata, report_ctx)
        # Presentation telemetry only: the REAL patched prompt after the loop.
        report.after_system_prompt = current_prompt
        _stamp_remediation_effectiveness(
            report,
            original_prompt=system_prompt,
            current_prompt=current_prompt,
            original_policy=sp,
            current_policy=current_policy,
            applied_ops=applied_ops,
            rejected_ops=rejected_ops,
        )
        return _stamp(report)

    except (SchemaContractError, ValidationError) as exc:
        # 13. Any unrecoverable TUNING/PATCH schema failure -> HUMAN_REVIEW_REQUIRED.
        # A ValidationError here can only come from validating an LLM-proposed
        # patch's effect (the deterministic baseline never raises one); it is
        # converted to a fail-safe partial report rather than crashing the run.
        # Genuine programming errors (other exception types) are NOT swallowed.
        return _stamp(
            _human_review_report(
                stage, exc, before_results, business_context_text, fallback_ctx=report_ctx
            )
        )
