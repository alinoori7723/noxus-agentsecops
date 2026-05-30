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

from .agents import (
    PolicyTuningAgent,
    RedTeamAgent,
    SemanticJudgeAgent,
    SEMANTIC_JUDGE_PROBE_TYPES,
)
from .constants import MAX_TUNING_ITERATIONS
from .evaluator import DeterministicEvaluator
from .json_contracts import SchemaContractError
from .llm_provider import LLMProvider
from .patch_engine import apply_patch_set
from .patch_mapper import generate_patches_from_findings
from .policy_loader import validate_policy
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
    patched_prompt, patched_policy_dict = apply_patch_set(
        system_prompt, sp.model_dump(), patch_set
    )
    patched_policy = validate_policy(patched_policy_dict)

    after_results = evaluator.evaluate(probes, patched_prompt, patched_policy)

    return build_report(
        before_results=before_results,
        after_results=after_results,
        patch_set=patch_set,
        business_context_text=business_context_text,
        human_review_requirements=patched_policy.human_review.required_categories,
    )


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


def _human_review_report(
    stage: str,
    error: Exception,
    before_results: Optional[list[ProbeResult]],
    business_context_text: str,
) -> ReadinessReport:
    before = before_results or []
    open_risk = (
        f"SchemaContractError at stage '{stage}': {error}. "
        "LLM execution aborted; no patches applied."
    )
    return ReadinessReport(
        probes_run=[r.probe_id for r in before],
        before_results=before,
        after_results=[],
        patch_operations_applied=[],
        before_score=score_from_results(before) if before else 0,
        after_score=0,
        readiness_state=ReadinessState.HUMAN_REVIEW_REQUIRED,
        open_risks=[open_risk],
        human_review_requirements=["schema_contract_failure"],
        metadata=ReportMetadata(
            business_context_text=business_context_text,
            mode="agent_assisted",
            tuning_iterations=0,
        ),
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
    before_results: Optional[list[ProbeResult]] = None
    stage = "input_validation"
    try:
        sp = _as_policy(policy)
        evaluator = DeterministicEvaluator()
        judge = SemanticJudgeAgent(provider, judge_model)
        tuner = PolicyTuningAgent(provider, tuning_model)

        # 2. Red team probes + 3. deterministic baseline probes (regression).
        stage = "red_team_generation"
        red = RedTeamAgent(provider, red_model)
        agent_probes = red.generate_probes(system_prompt, sp, business_context_text)
        probes = get_probes() + agent_probes

        current_prompt = system_prompt
        current_policy = sp

        # 4-7. Simulate + deterministic evaluate + semantic supplement.
        results = evaluator.evaluate(probes, current_prompt, current_policy)
        stage = "semantic_judge"
        results = _apply_semantic_judge(
            judge, probes, results, current_policy, current_prompt
        )
        before_results = results

        applied_ops = []
        iterations_done = 0
        # 12. Bounded by MAX_TUNING_ITERATIONS.
        while iterations_done < MAX_TUNING_ITERATIONS:
            findings = [f for r in results for f in r.findings]
            if not findings:
                break
            # 8-9. Propose + validate PatchSet (agent never applies patches).
            stage = "policy_tuning"
            patch_set = tuner.propose_patches(findings, current_policy, current_prompt)
            # 10. Deterministic patch engine is the ONLY applier.
            stage = "patch_application"
            new_prompt, new_policy_dict = apply_patch_set(
                current_prompt, current_policy.model_dump(), patch_set
            )
            current_prompt = new_prompt
            current_policy = validate_policy(new_policy_dict)
            applied_ops.extend(patch_set.operations)
            iterations_done += 1
            # 11. Rerun probes (+ semantic supplement).
            results = evaluator.evaluate(probes, current_prompt, current_policy)
            stage = "semantic_judge"
            results = _apply_semantic_judge(
                judge, probes, results, current_policy, current_prompt
            )

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
        return report

    except SchemaContractError as exc:
        # 13. Any unrecoverable schema failure -> HUMAN_REVIEW_REQUIRED.
        return _human_review_report(stage, exc, before_results, business_context_text)
