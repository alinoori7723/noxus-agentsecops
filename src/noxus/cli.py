"""Local deterministic CLI smoke flow for Noxus AgentSecOps Milestone 1.

Runs the full attack -> evaluate -> patch -> retest loop with no LLM, no
network, and no cloud calls.
"""

from __future__ import annotations

import argparse
import sys

from .evaluator import DeterministicEvaluator
from .patch_engine import apply_patch_set
from .patch_mapper import generate_patches_from_findings
from .policy_loader import load_text_file, load_yaml_policy, validate_policy
from .probe_registry import get_probes
from .report import build_report, render_cli_report
from .schemas import ReadinessReport


def run_pipeline(
    system_prompt_path: str,
    policy_path: str,
    business_context_path: str,
) -> ReadinessReport:
    """Execute the deterministic before/after loop and return the report."""
    # 1. Load inputs.
    system_prompt = load_text_file(system_prompt_path)
    raw_policy = load_yaml_policy(policy_path)
    # 3. business_context.md is documentation-only metadata.
    business_context_text = load_text_file(business_context_path)

    # 2. Validate the YAML policy.
    policy = validate_policy(raw_policy)

    # 4. Fixed probe registry.
    probes = get_probes()
    evaluator = DeterministicEvaluator()

    # 5. Before-state evaluation through the target simulator.
    before_results = evaluator.evaluate(probes, system_prompt, policy)

    # 7. Generate deterministic patches strictly from the emitted findings.
    before_findings = [f for r in before_results for f in r.findings]
    patch_set = generate_patches_from_findings(before_findings)

    # 8-9. Apply patches and validate the patched policy.
    patched_prompt, patched_policy_dict = apply_patch_set(
        system_prompt, policy.model_dump(), patch_set
    )
    patched_policy = validate_policy(patched_policy_dict)

    # 10. Re-run the same probes with the patched prompt/policy.
    after_results = evaluator.evaluate(probes, patched_prompt, patched_policy)

    # Build the before/after report.
    return build_report(
        before_results=before_results,
        after_results=after_results,
        patch_set=patch_set,
        business_context_text=business_context_text,
        human_review_requirements=patched_policy.human_review.required_categories,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noxus",
        description="Noxus AgentSecOps — Milestone 1 deterministic skeleton.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run the deterministic before/after loop.")
    run.add_argument("--system-prompt", required=True)
    run.add_argument("--policy", required=True)
    run.add_argument("--business-context", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns 0 on success, non-zero on errors."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            report = run_pipeline(
                system_prompt_path=args.system_prompt,
                policy_path=args.policy,
                business_context_path=args.business_context,
            )
        except Exception as exc:  # schema/validation/runtime errors -> non-zero.
            print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

        print(render_cli_report(report))
        # Skeleton ran successfully end-to-end; open risks are reported honestly
        # above, not treated as a process failure.
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
