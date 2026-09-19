from __future__ import annotations

from typing import Any, Literal

from pydantic import ValidationError

from .agents import (
    SEMANTIC_JUDGE_PROBE_TYPES,
    PolicyTuningAgent,
    RedTeamAgent,
    SemanticJudgeAgent,
)
from .constants import MAX_TUNING_ITERATIONS
from .errors import SchemaContractError
from .evaluator import DeterministicEvaluator
from .json_contracts import sanitize_excerpt
from .llm_provider import LLMProvider
from .llm_runtime import (
    RoleBoundProvider,
    RoleProviderError,
    RoleTimeoutError,
    TimeoutConfig,
)
from .patch_engine import apply_patch_set
from .patch_mapper import generate_patches_from_findings
from .policy_loader import validate_policy
from .probe_registry import get_probes
from .remediation import attach_patch_lineage
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
    provider: LLMProvider | None = None,
    red_model: str = "gemini-3.5-flash",
    judge_model: str = "gemini-3.5-flash",
    tuning_model: str = "gemini-3.1-pro-preview",
    timeout_config: TimeoutConfig | None = None,
    tuning_fallback_model: str | None = None,
    provider_type: str | None = None,
) -> ReadinessReport:

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
            timeout_config or TimeoutConfig.from_env(),
            tuning_fallback_model,
            provider_type,
        )
    raise ValueError(f"Unknown mode: {mode!r}")


def _run_deterministic(
    system_prompt: str, policy: Any, business_context_text: str
) -> ReadinessReport:
    sp = _as_policy(policy)
    probes = get_probes()
    evaluator = DeterministicEvaluator()

    before_results = evaluator.evaluate(probes, system_prompt, sp)
    before_findings = [f for r in before_results for f in r.findings]

    patch_set = generate_patches_from_findings(before_findings)

    linked, unlinked = attach_patch_lineage(patch_set.operations, before_findings)
    patch_set = PatchSet(operations=linked)
    patched_prompt, patched_policy_dict = apply_patch_set(system_prompt, sp.model_dump(), patch_set)
    patched_policy = validate_policy(patched_policy_dict)

    after_results = evaluator.evaluate(probes, patched_prompt, patched_policy)

    report = build_report(
        before_results=before_results,
        after_results=after_results,
        patch_set=patch_set,
        business_context_text=business_context_text,
        human_review_requirements=patched_policy.human_review.required_categories,
    )

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


def _semantic_finding(probe: Probe, judgment) -> Finding:
    return Finding(
        finding_type=judgment.suggested_finding_type or f"{probe.probe_type.value}_semantic",
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

    merged: list[ProbeResult] = []
    for probe, result in zip(probes, results, strict=True):
        if probe.probe_type not in SEMANTIC_JUDGE_PROBE_TYPES:
            merged.append(result)
            continue
        judgment = judge.judge(
            probe, result.target_response, result.findings, policy, system_prompt
        )
        if not judgment.semantic_violation:
            merged.append(result)
            continue

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

    report.metadata.patched_system_prompt_effective = current_prompt != original_prompt
    report.metadata.patched_policy_effective = (
        current_policy.model_dump() != original_policy.model_dump()
    )
    report.metadata.patch_application_count = len(applied_ops)
    report.metadata.rejected_proposal_count = len(rejected_ops)
    report.rejected_patch_operations = list(rejected_ops)


def _stamp_red_fallback(metadata: ReportMetadata, ctx: dict | None) -> None:

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
    before_results: list[ProbeResult] | None,
    business_context_text: str,
    fallback_ctx: dict | None = None,
) -> ReadinessReport:

    before = before_results or []

    safe_error = sanitize_excerpt(str(error))
    open_risks = [
        f"Agent-assisted stage '{stage}' failed schema validation: {safe_error}. "
        "LLM execution aborted; no patches applied. The deterministic baseline "
        "below is preserved."
    ]

    for r in before:
        for f in r.findings:
            open_risks.append(f"{f.probe_id}: {f.finding_type} ({f.severity.value}) — {f.evidence}")

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


def _timeout_message(diag: dict) -> str:

    label = diag["role_label"]
    model = diag.get("model") or "the configured model"
    if diag.get("is_timeout"):
        retries = diag.get("retry_count", 0)
        retry_phrase = (
            "no retries" if retries == 0 else f"{retries} retr{'y' if retries == 1 else 'ies'}"
        )
        secs = diag.get("timeout_seconds")
        secs_phrase = f"{secs:.0f}s" if isinstance(secs, (int, float)) else "the role timeout"
        return (
            f"LLM request timed out during {label} using {model} "
            f"(timeout {secs_phrase}, {retry_phrase})."
        )
    return f"LLM provider error during {label} using {model}: {diag.get('message', '')}".strip()


def _timeout_human_review_report(
    stage: str,
    error,
    before_results: list[ProbeResult] | None,
    business_context_text: str,
    *,
    fatal: bool = True,
) -> ReadinessReport:

    before = before_results or []
    diag = error.diagnostics()
    msg = _timeout_message(diag)
    open_risks = [
        f"Agent-assisted stage '{stage}' did not complete: {msg} "
        "LLM execution aborted; no patches applied. The deterministic baseline "
        "below is preserved."
    ]
    for r in before:
        for f in r.findings:
            open_risks.append(f"{f.probe_id}: {f.finding_type} ({f.severity.value}) — {f.evidence}")
    metadata = ReportMetadata(
        business_context_text=business_context_text,
        mode="agent_assisted",
        tuning_iterations=0,
        failed_stage=stage,
        failed_role=diag.get("failed_role") or _STAGE_ROLE.get(stage),
        timeout_failed_role=diag.get("failed_role"),
        timeout_failed_stage=stage,
        timeout_provider_type=diag.get("provider_type"),
        timeout_model=diag.get("model"),
        timeout_seconds=diag.get("timeout_seconds"),
        timeout_retry_count=diag.get("retry_count", 0),
        timeout_message=msg,
        timeout_fatal=fatal,
    )
    return ReadinessReport(
        probes_run=[r.probe_id for r in before],
        before_results=before,
        after_results=[],
        patch_operations_applied=[],
        before_score=score_from_results(before) if before else 0,
        after_score=0,
        readiness_state=ReadinessState.HUMAN_REVIEW_REQUIRED,
        open_risks=open_risks,
        human_review_requirements=["llm_timeout"],
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
    timeout_config: TimeoutConfig,
    tuning_fallback_model: str | None,
    provider_type: str | None,
) -> ReadinessReport:

    sp = _as_policy(policy)

    evaluator = DeterministicEvaluator()

    def _role_provider(role: str) -> RoleBoundProvider:
        return RoleBoundProvider(
            provider,
            role=role,
            provider_type=provider_type,
            timeout=timeout_config.timeout_for(role),
            max_retries=timeout_config.max_retries,
            backoff_seconds=timeout_config.backoff_seconds,
        )

    red_provider = _role_provider("red")
    judge_provider = _role_provider("judge")
    tuning_provider = _role_provider("tuning")
    judge = SemanticJudgeAgent(judge_provider, judge_model)
    tuner = PolicyTuningAgent(tuning_provider, tuning_model)

    fallback_tuner: PolicyTuningAgent | None = None
    if tuning_fallback_model:
        fallback_tuner = PolicyTuningAgent(_role_provider("tuning"), tuning_fallback_model)

    tuning_fallback_state: dict = {}

    current_prompt = system_prompt
    current_policy = sp

    baseline_probes = get_probes()
    baseline_results = evaluator.evaluate(baseline_probes, current_prompt, current_policy)
    baseline_findings = [f for r in baseline_results for f in r.findings]

    red_team_status = "used"
    fallback_ctx: dict | None = None
    continued_after_red_failure = False
    before_results: list[ProbeResult] = baseline_results

    probes = baseline_probes
    try:
        red = RedTeamAgent(red_provider, red_model)
        agent_probes = red.generate_probes(system_prompt, sp, business_context_text)
        probes = baseline_probes + agent_probes
    except (RoleTimeoutError, RoleProviderError) as red_to:
        if not baseline_findings:
            raise
        report = _timeout_human_review_report(
            "red_team_generation", red_to, baseline_results, business_context_text
        )
        report.metadata.evidence_basis = "deterministic_baseline"
        report.metadata.red_team_status = "failed"
        return report
    except (SchemaContractError, ValidationError) as red_exc:
        red_team_status = "failed"
        red_excerpt = getattr(red_exc, "raw_excerpt", None) or sanitize_excerpt(str(red_exc))
        if not baseline_findings:
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

            report.metadata.evidence_basis = "deterministic_baseline"
            return report

        continued_after_red_failure = True
        probes = baseline_probes
        fallback_ctx = {
            "red_team_status": "failed",
            "fallback_used": "deterministic_baseline",
            "fallback_reason": "red_team_schema_contract_failure",
            "continued_after_red_failure": True,
            "red_team_failure_excerpt": red_excerpt,
        }

    if fallback_ctx is None and red_team_status == "used":
        report_ctx = None
    else:
        report_ctx = fallback_ctx

    if continued_after_red_failure:
        evidence_basis = "degraded_fallback"
        semantic_judge_status: str | None = "skipped"
    else:
        evidence_basis = "red_team_augmented"
        semantic_judge_status = "used"
    judge_failed = False
    judge_excerpt: str | None = None
    judge_timeout_diag: dict | None = None

    def _maybe_apply_judge(results_in: list[ProbeResult]) -> list[ProbeResult]:
        nonlocal judge_failed, judge_excerpt, semantic_judge_status, judge_timeout_diag

        if continued_after_red_failure or judge_failed:
            return results_in
        try:
            return _apply_semantic_judge(judge, probes, results_in, current_policy, current_prompt)
        except (RoleTimeoutError, RoleProviderError) as exc:
            judge_failed = True
            semantic_judge_status = "failed"
            judge_timeout_diag = exc.diagnostics()
            judge_excerpt = _timeout_message(judge_timeout_diag)
            return results_in
        except (SchemaContractError, ValidationError) as exc:
            judge_failed = True
            semantic_judge_status = "failed"
            judge_excerpt = getattr(exc, "raw_excerpt", None) or sanitize_excerpt(str(exc))
            return results_in

    def _stamp_fallback(report: ReadinessReport) -> None:

        if not tuning_fallback_state.get("used"):
            return
        m = report.metadata
        m.tuning_fallback_used = True
        m.tuning_fallback_original_model = tuning_fallback_state.get("original_model")
        m.tuning_fallback_model = tuning_fallback_state.get("fallback_model")
        m.tuning_fallback_reason = tuning_fallback_state.get("reason")

        diag = tuning_fallback_state.get("original_diag")
        if diag and not m.timeout_fatal:
            m.timeout_failed_role = diag.get("failed_role")
            m.timeout_failed_stage = "policy_tuning"
            m.timeout_provider_type = diag.get("provider_type")
            m.timeout_model = diag.get("model")
            m.timeout_seconds = diag.get("timeout_seconds")
            m.timeout_retry_count = diag.get("retry_count", 0)
            m.timeout_message = _timeout_message(diag)
            m.timeout_fatal = False

    def _stamp(report: ReadinessReport) -> ReadinessReport:
        report.metadata.semantic_judge_status = semantic_judge_status
        report.metadata.semantic_judge_failure_excerpt = judge_excerpt
        report.metadata.evidence_basis = evidence_basis

        if judge_timeout_diag is not None and not report.metadata.timeout_fatal:
            report.metadata.timeout_failed_role = judge_timeout_diag.get("failed_role")
            report.metadata.timeout_failed_stage = "semantic_judge"
            report.metadata.timeout_provider_type = judge_timeout_diag.get("provider_type")
            report.metadata.timeout_model = judge_timeout_diag.get("model")
            report.metadata.timeout_seconds = judge_timeout_diag.get("timeout_seconds")
            report.metadata.timeout_retry_count = judge_timeout_diag.get("retry_count", 0)
            report.metadata.timeout_message = _timeout_message(judge_timeout_diag)
            report.metadata.timeout_fatal = False
        _stamp_fallback(report)
        return report

    stage = "policy_tuning"
    try:
        results = evaluator.evaluate(probes, current_prompt, current_policy)

        results = _maybe_apply_judge(results)
        before_results = results

        applied_ops = []
        rejected_ops = []
        iterations_done = 0

        while iterations_done < MAX_TUNING_ITERATIONS:
            findings = [f for r in results for f in r.findings]
            if not findings:
                break

            stage = "policy_tuning"
            try:
                patch_set = tuner.propose_patches(findings, current_policy, current_prompt)
            except (RoleTimeoutError, RoleProviderError) as tune_to:
                if fallback_tuner is None:
                    raise
                tuning_fallback_state.update(
                    {
                        "used": True,
                        "original_model": tuning_model,
                        "fallback_model": tuning_fallback_model,
                        "reason": "timeout",
                        "original_diag": tune_to.diagnostics(),
                    }
                )

                patch_set = fallback_tuner.propose_patches(findings, current_policy, current_prompt)

            linked, unlinked = attach_patch_lineage(patch_set.operations, findings)
            rejected_ops.extend(unlinked)

            stage = "patch_application"
            new_prompt, new_policy_dict = apply_patch_set(
                current_prompt, current_policy.model_dump(), PatchSet(operations=linked)
            )
            current_prompt = new_prompt
            current_policy = validate_policy(new_policy_dict)
            applied_ops.extend(linked)
            iterations_done += 1

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

    except (RoleTimeoutError, RoleProviderError) as to_exc:
        report = _timeout_human_review_report(stage, to_exc, before_results, business_context_text)
        report.metadata.red_team_status = red_team_status
        _stamp_red_fallback(report.metadata, report_ctx)
        return _stamp(report)

    except (SchemaContractError, ValidationError) as exc:
        report = _human_review_report(
            stage, exc, before_results, business_context_text, fallback_ctx=report_ctx
        )
        report.metadata.red_team_status = red_team_status
        return _stamp(report)
