"""Local deterministic / agent-assisted CLI for Noxus AgentSecOps.

Deterministic mode reproduces Milestone 1 exactly and needs no credentials.
Agent-assisted mode layers schema-bound LLM agents on top and requires a
LiteLLM-compatible endpoint configured via environment variables. Tests inject a
FakeLLMProvider instead of making real network calls.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Callable, Optional

from .llm_provider import LLMProvider, LiteLLMProvider, ProviderError
from .orchestrator import run_readiness_assessment
from .policy_loader import load_text_file, load_yaml_policy, validate_policy
from .report import render_cli_report
from .schemas import ReadinessReport


def run_pipeline(
    system_prompt_path: str,
    policy_path: str,
    business_context_path: str,
) -> ReadinessReport:
    """Milestone 1 deterministic pipeline (kept for backwards compatibility)."""
    system_prompt = load_text_file(system_prompt_path)
    raw_policy = load_yaml_policy(policy_path)
    business_context_text = load_text_file(business_context_path)
    # Validate before handing off (raises on malformed policy).
    validate_policy(raw_policy)
    return run_readiness_assessment(
        system_prompt=system_prompt,
        policy=raw_policy,
        business_context_text=business_context_text,
        mode="deterministic",
    )


def _build_provider_from_env() -> LLMProvider:
    """Construct a LiteLLMProvider from environment variables, or raise."""
    base_url = os.environ.get("NOXUS_LLM_BASE_URL")
    api_key = os.environ.get("NOXUS_LLM_API_KEY")
    if not base_url or not api_key:
        raise ProviderError(
            "agent-assisted mode requires NOXUS_LLM_BASE_URL and "
            "NOXUS_LLM_API_KEY environment variables."
        )
    return LiteLLMProvider(base_url, api_key)


def _models_from_env() -> dict[str, str]:
    return {
        "red_model": os.environ.get("NOXUS_RED_MODEL", "gemini-3.5-flash"),
        "judge_model": os.environ.get("NOXUS_JUDGE_MODEL", "gemini-3.5-flash"),
        "tuning_model": os.environ.get("NOXUS_TUNING_MODEL", "gemini-3.1-pro-preview"),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noxus",
        description="Noxus AgentSecOps — deterministic / agent-assisted readiness tester.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run the readiness assessment loop.")
    run.add_argument("--system-prompt", required=True)
    run.add_argument("--policy", required=True)
    run.add_argument("--business-context", required=True)
    run.add_argument(
        "--mode",
        choices=["deterministic", "agent-assisted"],
        default="deterministic",
        help="Execution mode (default: deterministic).",
    )
    return parser


def main(
    argv: Optional[list[str]] = None,
    provider_factory: Optional[Callable[[], LLMProvider]] = None,
) -> int:
    """CLI entrypoint. Returns 0 on success, non-zero on errors.

    ``provider_factory`` lets tests inject a FakeLLMProvider without touching
    the environment or the network.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command != "run":
        parser.print_help()
        return 1

    try:
        system_prompt = load_text_file(args.system_prompt)
        raw_policy = load_yaml_policy(args.policy)
        business_context_text = load_text_file(args.business_context)
        validate_policy(raw_policy)

        if args.mode == "deterministic":
            report = run_readiness_assessment(
                system_prompt=system_prompt,
                policy=raw_policy,
                business_context_text=business_context_text,
                mode="deterministic",
            )
        else:  # agent-assisted
            try:
                provider = (provider_factory or _build_provider_from_env)()
            except ProviderError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 2
            report = run_readiness_assessment(
                system_prompt=system_prompt,
                policy=raw_policy,
                business_context_text=business_context_text,
                mode="agent_assisted",
                provider=provider,
                **_models_from_env(),
            )
    except Exception as exc:  # schema/validation/runtime errors -> non-zero.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(render_cli_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
