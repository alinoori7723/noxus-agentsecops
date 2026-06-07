"""Pure-Python API core for the Noxus AgentSecOps web UI.

This module contains NO web-framework imports. It is the testable seam between
the React frontend's HTTP contract and the accepted Noxus orchestrator. The thin
``api_server`` module wraps these functions with HTTP routes and static serving.

Honest-labeling, scoring, evaluator, agent, and patch behavior all live in the
unchanged core; this module only adapts inputs/outputs. Provider API keys are
used in memory for a single request and are never logged, returned, or persisted.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

from . import ui_formatters
from .constants import MAX_TUNING_ITERATIONS
from .llm_provider import (
    GeminiNativeProvider,
    LiteLLMProvider,
    LLMProvider,
    ProviderError,
    ProviderTimeoutError,
)
from .llm_runtime import (
    ROLE_LABEL,
    RoleProviderError,
    RoleTimeoutError,
    TimeoutConfig,
    tuning_fallback_model_from_env,
)
from .orchestrator import run_readiness_assessment
from .policy_loader import validate_policy

_SAMPLES = Path(__file__).resolve().parent / "samples"

PRODUCT_NAME = "Noxus AgentSecOps"

# Provider types the frontend may choose for agent-assisted mode.
PROVIDER_LOCAL = "local_openai_compatible"
PROVIDER_OPENAI = "openai_compatible"
PROVIDER_GEMINI = "gemini_native"
PROVIDER_TYPES = (PROVIDER_LOCAL, PROVIDER_OPENAI, PROVIDER_GEMINI)

DEFAULT_LOCAL_BASE_URL = "http://localhost:4000/v1"

# Opt-in local audit export is confined to this directory (env-overridable). The
# client may never supply a path — only a sanitized filename under this root.
DEFAULT_AUDIT_DIR = "outputs/audit"
DEFAULT_AUDIT_FILENAME = "readiness_reports.jsonl"

# Convenience model presets surfaced to the UI. These are editable defaults, NOT
# availability guarantees — model ids change over time and users can type custom.
GEMINI_MODEL_PRESETS = (
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
)
DEFAULT_MODELS = {
    "red_model": "gemini-3.5-flash",
    "judge_model": "gemini-3.5-flash",
    "tuning_model": "gemini-3.1-pro-preview",
}

# The three agent roles and the human-readable purpose of each model.
AGENT_ROLES = ("red", "judge", "tuning")
ROLE_MODEL_KEY = {"red": "red_model", "judge": "judge_model", "tuning": "tuning_model"}
ROLE_PURPOSE = {
    "red": "Generates adversarial probes",
    "judge": "Reviews semantic violations",
    "tuning": "Proposes schema-bound patches",
}


class ApiError(Exception):
    """A request-level error carrying a safe HTTP status code and message.

    The ``message`` is guaranteed safe to return to the client: it never
    contains the caller's API key (provider construction errors are rephrased).
    An optional ``code`` + ``details`` carry safe, structured context (e.g. the
    unsupported policy keys) so the UI can render a clean, friendly error.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.details = details or {}


# --------------------------------------------------------------------------- #
# Request models (pydantic — no web framework dependency)
# --------------------------------------------------------------------------- #
class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_type: str = PROVIDER_LOCAL
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    red_model: Optional[str] = None
    judge_model: Optional[str] = None
    tuning_model: Optional[str] = None


class RunAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = "deterministic"
    system_prompt: str = ""
    security_policy_yaml: str = ""
    business_context: str = ""
    provider_config: Optional[ProviderConfig] = None


class ProviderTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_config: ProviderConfig
    # Which agent-role models to probe. Defaults to all three; a subset is valid.
    models_to_test: list[str] = Field(default_factory=lambda: list(AGENT_ROLES))


class AuditExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The raw ReadinessReport (as returned under response["report"]). Opt-in only.
    # The client may suggest a *filename* (sanitized server-side); it can NEVER
    # supply a path. Writes are confined to the server's configured audit dir.
    # ``output_path`` was removed to prevent caller-controlled filesystem writes;
    # sending it is rejected by ``extra="forbid"``. The report carries no API key.
    report: dict
    filename: Optional[str] = None


# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #
_REDACTED = "***REDACTED***"


def redact_provider_config(config: Any) -> dict:
    """Return a log-safe copy of a provider config with the api_key removed.

    Accepts a ProviderConfig, a plain dict, or None. The api_key is replaced
    with a redaction marker (or dropped) so it can never reach logs.
    """
    if config is None:
        return {}
    data = config.model_dump() if isinstance(config, BaseModel) else dict(config)
    if data.get("api_key"):
        data["api_key"] = _REDACTED
    return data


def redact_request(req: "RunAssessmentRequest") -> dict:
    """Return a log-safe view of a run request (api_key never included)."""
    return {
        "mode": req.mode,
        "system_prompt_chars": len(req.system_prompt or ""),
        "security_policy_yaml_chars": len(req.security_policy_yaml or ""),
        "business_context_chars": len(req.business_context or ""),
        "provider_config": redact_provider_config(req.provider_config),
    }


# --------------------------------------------------------------------------- #
# Endpoints (pure logic)
# --------------------------------------------------------------------------- #
def health_payload() -> dict:
    return {"ok": True, "product": PRODUCT_NAME, "mode": "api"}


def _read_sample(name: str) -> str:
    try:
        return (_SAMPLES / name).read_text(encoding="utf-8")
    except OSError:
        return ""


def sample_inputs() -> dict:
    """Return the bundled sample inputs for the configuration workspace."""
    return {
        "system_prompt": _read_sample("system_prompt.txt"),
        "security_policy_yaml": _read_sample("security_policy.yaml"),
        # Clean demo fixture: a realistic untrusted SupportBot case bundle. It
        # describes the TARGET app's material and contains target-facing
        # adversarial content; it never instructs the auditor what to detect.
        "business_context": _read_sample("support_case_base.md"),
    }


def proof_indicators(test_count: Optional[int] = None) -> dict:
    """Non-secret proof indicators surfaced in the UI shell."""
    return {
        "test_count": test_count,
        "max_tuning_iterations": MAX_TUNING_ITERATIONS,
        "schema_bound_agents": True,
        "deterministic_patch_engine": True,
        "local_jsonl_audit_export": True,
    }


POLICY_SCHEMA_MESSAGE = (
    "Security Policy YAML does not match the supported Noxus policy schema."
)
# A real, minimal policy that validates against SecurityPolicy. Shown to the user
# as the expected shape (the supported top-level keys are derived from the model).
MINIMAL_POLICY_EXAMPLE = (
    "sensitive_data:\n"
    "  block: []\n"
    "  mask: []\n"
    "prompt_injection:\n"
    "  mode: basic\n"
    "  detect_indirect_instructions: false\n"
    "output_policy:\n"
    "  block_confidential: true\n"
    "human_review:\n"
    "  required_categories: []\n"
)


def supported_policy_keys() -> list[str]:
    """The supported top-level keys, sourced from the SecurityPolicy schema."""
    from .schemas import SecurityPolicy

    return list(SecurityPolicy.model_fields.keys())


def _policy_schema_error(raw: dict, exc: Exception) -> ApiError:
    """Build a clean, structured policy-validation error (no raw Pydantic dump)."""
    allowed = supported_policy_keys()
    unsupported: list[str] = []
    # Prefer precise, structured locations from Pydantic (incl. nested keys).
    errors = getattr(exc, "errors", None)
    if callable(errors):
        for e in exc.errors():
            if e.get("type") == "extra_forbidden":
                loc = ".".join(str(p) for p in e.get("loc", ()))
                if loc:
                    unsupported.append(loc)
    if not unsupported and isinstance(raw, dict):
        unsupported = [k for k in raw.keys() if k not in allowed]
    return ApiError(
        400,
        POLICY_SCHEMA_MESSAGE,
        code="policy_schema",
        details={
            "unsupported_keys": unsupported,
            "allowed_keys": allowed,
            "example_yaml": MINIMAL_POLICY_EXAMPLE,
        },
    )


def _parse_policy(security_policy_yaml: str) -> dict:
    try:
        raw = yaml.safe_load(security_policy_yaml) or {}
    except yaml.YAMLError as exc:
        raise ApiError(
            400,
            "Security Policy YAML could not be parsed. Please check the YAML syntax.",
            code="policy_yaml",
            details={"example_yaml": MINIMAL_POLICY_EXAMPLE},
        ) from exc
    if not isinstance(raw, dict):
        raise ApiError(
            400,
            "Security Policy YAML must be a mapping of keys to values.",
            code="policy_schema",
            details={
                "unsupported_keys": [],
                "allowed_keys": supported_policy_keys(),
                "example_yaml": MINIMAL_POLICY_EXAMPLE,
            },
        )
    try:
        validate_policy(raw)  # raise early on a malformed policy
    except Exception as exc:  # pydantic ValidationError -> clean structured 400
        raise _policy_schema_error(raw, exc) from exc
    return raw


BASE_URL_SCHEME_ERROR = "Base URL must include http:// or https://"


def _validate_base_url(base_url: str) -> None:
    """Ensure an OpenAI-style base URL has an http(s) scheme and a host.

    Raises a clean ApiError(400) instead of letting urllib raise an opaque
    'unknown url type: ...' error deep in the provider call.
    """
    from urllib.parse import urlparse

    parsed = urlparse((base_url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiError(400, BASE_URL_SCHEME_ERROR)


def build_provider(config: Optional[ProviderConfig]) -> tuple[LLMProvider, dict]:
    """Build an LLM provider from a provider config. Returns (provider, models).

    Raises ApiError(400) with a safe message (never echoing the api key) when
    the configuration is missing or invalid.
    """
    if config is None:
        raise ApiError(
            400,
            "Agent-Assisted Mode requires provider_config "
            "(provider_type, api_key, and model names).",
        )
    provider_type = config.provider_type or PROVIDER_LOCAL
    if provider_type not in PROVIDER_TYPES:
        raise ApiError(
            400,
            f"Unknown provider_type {provider_type!r}. "
            f"Expected one of: {', '.join(PROVIDER_TYPES)}.",
        )
    if not config.api_key:
        raise ApiError(400, "Agent-Assisted Mode requires provider_config.api_key.")

    try:
        if provider_type == PROVIDER_GEMINI:
            provider: LLMProvider = GeminiNativeProvider(config.api_key)
        elif provider_type == PROVIDER_LOCAL:
            base_url = config.base_url or DEFAULT_LOCAL_BASE_URL
            _validate_base_url(base_url)
            provider = LiteLLMProvider(base_url, config.api_key)
        else:  # PROVIDER_OPENAI
            if not config.base_url:
                raise ApiError(
                    400, "openai_compatible provider requires a base_url."
                )
            _validate_base_url(config.base_url)
            provider = LiteLLMProvider(config.base_url, config.api_key)
    except ProviderError as exc:
        # ProviderError messages are constructed from non-secret fields only.
        raise ApiError(400, f"Invalid provider configuration: {exc}") from exc

    models = {
        "red_model": config.red_model or DEFAULT_MODELS["red_model"],
        "judge_model": config.judge_model or DEFAULT_MODELS["judge_model"],
        "tuning_model": config.tuning_model or DEFAULT_MODELS["tuning_model"],
    }
    return provider, models


def _ev(maybe_enum) -> str:
    """Return the .value of an enum, or str(value)."""
    return getattr(maybe_enum, "value", None) or str(maybe_enum)


def _semantic_judgment_source(report) -> str:
    """'llm' if any retained finding came from the semantic judge, else 'deterministic'."""
    for results in (report.before_results, report.after_results):
        for r in results:
            for f in r.findings:
                if _ev(f.detection_mode) == "semantic_llm":
                    return "llm"
    return "deterministic"


def build_agent_trace(report, mode: str, provider_config) -> dict:
    """Presentation-only trace of which LLM role did what (no scoring impact).

    Derived from the report plus the request's mode/provider_config. Contains NO
    API key and NO raw provider_config — only provider_type and model names.
    """
    is_agent = mode == "agent_assisted"
    pc = provider_config
    provider_type = (pc.provider_type if (is_agent and pc is not None) else None)

    def _model(role: str) -> Optional[str]:
        if not is_agent:
            return None
        key = ROLE_MODEL_KEY[role]
        return (getattr(pc, key, None) if pc else None) or DEFAULT_MODELS[key]

    meta = report.metadata
    patch_count = len(report.patch_operations_applied)
    before_probes = len(report.before_results)
    baseline_finding_count = sum(len(r.findings) for r in report.before_results)
    semantic_source = _semantic_judgment_source(report)
    # A schema-contract abort (not just a high-severity finding) is the only case
    # where the agent pipeline itself failed and routed to human review.
    schema_failure = "schema_contract_failure" in list(report.human_review_requirements)
    failed_role = getattr(meta, "failed_role", None)
    # Red-Team resilience telemetry: the Red Team may have FAILED yet the loop
    # CONTINUED on deterministic baseline evidence (a successful, honest run that
    # is visually distinct from a clean Red Team success).
    red_team_status = getattr(meta, "red_team_status", None)
    continued_after_red = bool(getattr(meta, "continued_after_red_failure", False))
    fallback_used = getattr(meta, "fallback_used", None)
    fallback_reason = getattr(meta, "fallback_reason", None)
    # LLM timeout telemetry. A FATAL timeout routes to HUMAN_REVIEW_REQUIRED and
    # is rendered like a pipeline failure (failing role -> "failed", with a
    # timeout-specific summary); a non-fatal timeout (degraded judge / recovered
    # tuning fallback) is surfaced without failing the whole pipeline.
    timeout_role = getattr(meta, "timeout_failed_role", None)
    timeout_fatal = is_agent and bool(getattr(meta, "timeout_fatal", False))
    timeout_message = getattr(meta, "timeout_message", None)
    tuning_fallback_used = bool(getattr(meta, "tuning_fallback_used", False))
    tuning_fallback_model = getattr(meta, "tuning_fallback_model", None)
    # A red/tuning timeout sets red_team_status; do NOT route it through the
    # schema-failure red block (which has schema-specific wording).
    red_failed = is_agent and not timeout_fatal and (
        red_team_status == "failed" or (schema_failure and failed_role == "red")
    )
    # Semantic-Judge resilience telemetry: the judge may have FAILED its schema
    # contract yet the loop CONTINUED on deterministic + valid red-team evidence.
    semantic_judge_status = getattr(meta, "semantic_judge_status", None)
    judge_degraded = is_agent and not red_failed and semantic_judge_status == "failed"
    evidence_basis = getattr(meta, "evidence_basis", None)
    # Role pipeline order: red -> judge -> tuning. On a schema failure, the failing
    # role is "failed", earlier roles "used" (they completed), later roles "not_used".
    _ROLE_ORDER = {"red": 0, "judge": 1, "tuning": 2}
    pipeline_failed = schema_failure or timeout_fatal
    # A fatal timeout attributes the failure to its timeout_role; a schema failure
    # to failed_role.
    failing_role = timeout_role if timeout_fatal else failed_role
    failed_idx = _ROLE_ORDER.get(failing_role) if pipeline_failed else None

    def _agent_status(role: str, default_used: bool, default_not_used_summary: str,
                      used_summary: str) -> dict:
        idx = _ROLE_ORDER[role]
        if failed_idx is not None:
            if idx == failed_idx:
                if timeout_fatal:
                    return {"source": "llm", "status": "failed",
                            "summary": timeout_message
                            or f"{used_summary.split('.')[0]} — timed out."}
                return {"source": "llm", "status": "failed",
                        "summary": f"{used_summary.split('.')[0]} — failed schema validation."}
            if idx < failed_idx:
                return {"source": "llm", "status": "used", "summary": used_summary}
            return {"source": "llm", "status": "not_used",
                    "summary": "Not reached — an earlier agent stage failed."}
        return {"source": "llm",
                "status": "used" if default_used else "not_used",
                "summary": used_summary if default_used else default_not_used_summary}

    if red_failed:
        # Red Team failed its schema contract. Honest, distinct presentation:
        # never shown as a clean success and never as a fabricated probe run.
        red = {
            "source": "llm",
            "status": "failed",
            "summary": (
                "Generated probes failed schema validation — continued using "
                "deterministic baseline evidence."
                if continued_after_red
                else "Generated probes failed schema validation — no "
                "deterministic baseline findings to fall back to."
            ),
        }
        if continued_after_red:
            # Loop degraded to the deterministic baseline; the judge is skipped
            # and tuning still runs from deterministic baseline findings.
            judge = {
                "source": "llm",
                "status": "skipped",
                "summary": (
                    "Skipped — ran on deterministic baseline evidence after the "
                    "Red Team Agent failed."
                ),
            }
            if schema_failure and failed_role == "tuning":
                tuning = {
                    "source": "llm",
                    "status": "failed",
                    "summary": "Proposed a patch that failed schema validation.",
                }
            elif patch_count > 0:
                tuning = {
                    "source": "llm",
                    "status": "used",
                    "summary": (
                        f"Proposed a schema-bound PatchSet ({patch_count} "
                        "operations) from deterministic baseline findings."
                    ),
                }
            else:
                tuning = {"source": "llm", "status": "not_used",
                          "summary": "Proposed no patches."}
        else:
            judge = {
                "source": "llm", "status": "not_used",
                "summary": "Not reached — the Red Team Agent failed and no "
                "deterministic baseline fallback was available.",
            }
            tuning = {
                "source": "llm", "status": "not_used",
                "summary": "Not reached — the Red Team Agent failed and no "
                "deterministic baseline fallback was available.",
            }
    elif is_agent:
        # Red Team
        red = _agent_status(
            "red", True,
            "Red team did not run.",
            "Generated structured probes on top of the deterministic baseline.",
        )
        # Semantic Judge — honest "failed" when it broke its contract but the
        # loop degraded and continued on deterministic + valid red-team evidence.
        if judge_degraded:
            judge = {
                "source": "llm",
                "status": "failed",
                "summary": (
                    timeout_message + " Continued on deterministic evidence."
                    if (timeout_role == "judge" and not timeout_fatal and timeout_message)
                    else "Evaluated semantic violations — failed schema validation; "
                    "continued on deterministic evidence (no semantic findings "
                    "fabricated)."
                ),
            }
        else:
            judge = _agent_status(
                "judge", semantic_source == "llm",
                "Ran, but added no semantic findings beyond deterministic checks.",
                "Evaluated semantic violations and added judged findings.",
            )
        # Policy Tuning (proposes the patch set)
        tuning = _agent_status(
            "tuning", patch_count > 0,
            "Proposed no patches.",
            f"Proposed a schema-bound PatchSet ({patch_count} operations).",
        )
        # If the primary tuning model timed out but a fallback recovered, say so
        # honestly (the original timeout is never hidden).
        if tuning_fallback_used and tuning.get("status") == "used":
            tuning["summary"] = (
                f"Policy Tuning Agent timed out on {_model('tuning')}; fallback "
                f"model {tuning_fallback_model} was used. {tuning['summary']}"
            )
    else:
        red = {
            "source": "deterministic_baseline",
            "status": "used",
            "summary": f"Ran {before_probes} deterministic baseline probes.",
        }
        judge = {"source": "deterministic", "status": "not_used",
                 "summary": "Semantic judge is not used in deterministic mode."}
        tuning = {"source": "deterministic_mapper",
                  "status": "used" if patch_count else "not_used",
                  "summary": f"Patches mapped deterministically from findings ({patch_count})."}

    stages = [
        {"stage": "red_team", "role": "red", "model": _model("red"),
         "provider_type": provider_type, **red},
        {"stage": "semantic_judge", "role": "judge", "model": _model("judge"),
         "provider_type": provider_type, **judge},
        {"stage": "policy_tuning", "role": "tuning", "model": _model("tuning"),
         "provider_type": provider_type, **tuning},
        {"stage": "patch_application", "role": None, "model": None,
         "provider_type": None, "source": "deterministic_engine",
         "status": "used" if patch_count else "not_used",
         "summary": f"Deterministic engine applied {patch_count} allowed patch operations."},
    ]
    return {
        "execution_mode": mode,
        "provider_type": provider_type,
        "red_model": _model("red"),
        "judge_model": _model("judge"),
        "tuning_model": _model("tuning"),
        "semantic_judgment_source": semantic_source,
        "patch_proposal_source": "llm" if is_agent else "deterministic_mapper",
        # Red-Team resilience trace (presentation-only). Lets the UI explain a
        # degraded-but-honest run distinct from a clean Red Team success.
        "fallback_used": fallback_used if red_failed else None,
        "fallback_reason": fallback_reason if red_failed else None,
        "continued_after_red_failure": continued_after_red,
        "baseline_probe_count": before_probes,
        "baseline_finding_count": baseline_finding_count,
        # Which evidence base the before/after metrics were computed over, and the
        # semantic-judge resilience status (so a degraded run is never silent).
        "evidence_basis": evidence_basis,
        "semantic_judge_status": semantic_judge_status,
        # Timeout/fallback resilience trace (presentation-only; never a secret).
        "timeout_failed_role": timeout_role,
        "timeout_fatal": timeout_fatal,
        "tuning_fallback_used": tuning_fallback_used,
        "tuning_fallback_model": tuning_fallback_model if tuning_fallback_used else None,
        "stages": stages,
    }


def build_assessment_response(report, *, mode=None, provider_config=None) -> dict:
    """Assemble the full UI display payload from a ReadinessReport.

    Reuses the pure-Python ui_formatters so all honest-labeling rules
    (CONDITIONAL_PASS, [DETERMINISTIC SIMULATION], [SEMANTIC LLM JUDGMENT],
    real [CRITICAL_SAFETY_RAILS] telemetry, visible open risks) are applied in
    exactly one place. Contains no API key. The agent trace is presentation-only.
    """
    effective_mode = mode or getattr(report.metadata, "mode", "deterministic")
    trace = build_agent_trace(report, effective_mode, provider_config)
    meta = report.metadata
    baseline_findings = sum(len(r.findings) for r in report.before_results)
    schema_failure = None
    if "schema_contract_failure" in list(report.human_review_requirements):
        schema_failure = {
            "failed_stage": getattr(meta, "failed_stage", None),
            "failed_role": getattr(meta, "failed_role", None),
            # Already sanitized (<=500 chars, secrets redacted) by json_contracts.
            "debug_excerpt": getattr(meta, "schema_failure_excerpt", None),
            "baseline_preserved": bool(report.before_results),
            "baseline_probe_count": len(report.before_results),
            "baseline_finding_count": baseline_findings,
            "reason": "schema contract failure",
        }
    # Red-Team diagnostics: present whenever the Red Team Agent failed its schema
    # contract — for BOTH a degraded-but-continued run (CONDITIONAL_PASS/PASS via
    # the deterministic baseline fallback) AND an abort. Honest, never hidden.
    red_team_failure = None
    if getattr(meta, "red_team_status", None) == "failed":
        red_team_failure = {
            "failed": True,
            "failed_stage": "red_team",
            "failed_role": "red",
            "source": "llm",
            "fallback_used": getattr(meta, "fallback_used", None),
            "fallback_reason": getattr(meta, "fallback_reason", None),
            "continued_after_red_failure": bool(
                getattr(meta, "continued_after_red_failure", False)
            ),
            "baseline_preserved": bool(report.before_results),
            "baseline_probe_count": len(report.before_results),
            "baseline_finding_count": baseline_findings,
            # Sanitized (<=500 chars, secrets redacted) by json_contracts.
            "debug_excerpt": getattr(meta, "red_team_failure_excerpt", None),
        }
    # Semantic-Judge diagnostics: present when the judge broke its schema contract
    # but the loop DEGRADED and continued on deterministic + valid red-team
    # evidence (no semantic findings fabricated). Symmetric with red_team_failure.
    semantic_judge_failure = None
    if getattr(meta, "semantic_judge_status", None) == "failed":
        semantic_judge_failure = {
            "failed": True,
            "failed_stage": "semantic_judge",
            "failed_role": "judge",
            "source": "llm",
            "fallback_basis": getattr(meta, "evidence_basis", None),
            "continued": True,
            "baseline_preserved": bool(report.before_results),
            "baseline_probe_count": len(report.before_results),
            "baseline_finding_count": baseline_findings,
            # Sanitized (<=500 chars, secrets redacted) by json_contracts.
            "debug_excerpt": getattr(meta, "semantic_judge_failure_excerpt", None),
        }
    # LLM TIMEOUT diagnostics (presentation-only). Present whenever a role's
    # provider call timed out — fatally (-> HUMAN_REVIEW_REQUIRED) or non-fatally
    # (a degraded judge supplement, or a tuning timeout recovered by fallback).
    # Carries NO api key and NO request body — only safe role/model diagnostics.
    timeout_failure = None
    if getattr(meta, "timeout_failed_role", None):
        timeout_failure = {
            "failed_role": meta.timeout_failed_role,
            "role_label": ROLE_LABEL.get(meta.timeout_failed_role, "LLM Agent"),
            "failed_stage": getattr(meta, "timeout_failed_stage", None),
            "provider_type": getattr(meta, "timeout_provider_type", None),
            "model": getattr(meta, "timeout_model", None),
            "timeout_seconds": getattr(meta, "timeout_seconds", None),
            "retry_count": getattr(meta, "timeout_retry_count", 0),
            "message": getattr(meta, "timeout_message", None),
            "fatal": bool(getattr(meta, "timeout_fatal", False)),
        }
    # Policy-Tuning fallback-model telemetry (Fix 4) — never silently hidden.
    tuning_fallback = None
    if getattr(meta, "tuning_fallback_used", False):
        tuning_fallback = {
            "used": True,
            "original_model": getattr(meta, "tuning_fallback_original_model", None),
            "fallback_model": getattr(meta, "tuning_fallback_model", None),
            "reason": getattr(meta, "tuning_fallback_reason", None),
        }
    # Non-breaking, top-level SUMMARY ALIASES. These are a flat convenience view
    # derived ENTIRELY from the same real report object (no new semantics, no
    # scoring change, no API key/provider config). The nested
    # readiness/metadata/report shapes are preserved unchanged above/below.
    after_finding_count = sum(len(r.findings) for r in report.after_results)
    rmeta = report.metadata
    summary_aliases = {
        "readiness_state": _ev(report.readiness_state),
        "before_score": report.before_score,
        "after_score": report.after_score,
        "patch_count": len(report.patch_operations_applied),
        "open_risk_count": len(report.open_risks),
        "finding_count": after_finding_count,
        "tuning_iterations": getattr(rmeta, "tuning_iterations", 0),
        "evidence_basis": getattr(rmeta, "evidence_basis", None),
        # Present (value) on a schema-contract abort, else None.
        "failed_stage": getattr(rmeta, "failed_stage", None),
        "failed_role": getattr(rmeta, "failed_role", None),
        # Remediation-effectiveness aliases (distinguish "applied" from "fixed").
        "resolved_probe_count": getattr(rmeta, "resolved_probe_count", 0),
        "unresolved_probe_count": getattr(rmeta, "unresolved_probe_count", 0),
        "resolved_finding_count": getattr(rmeta, "resolved_finding_count", 0),
        "unresolved_finding_count": getattr(rmeta, "unresolved_finding_count", 0),
        # Probe/finding mapping counts (Fix 4) — one probe can emit multiple
        # findings, so probe and finding counts differ. Exposed flatly so the
        # report can explain the difference.
        "baseline_probe_count": len(report.before_results),
        "baseline_failed_probe_count": sum(
            1 for r in report.before_results if not r.passed
        ),
        "baseline_finding_count": baseline_findings,
        # Instance-named aliases (Fix 2 & 5) — a finding instance is one emitted
        # finding; one probe may emit several.
        "baseline_finding_instance_count": baseline_findings,
        "retest_failed_probe_count": sum(
            1 for r in report.after_results if not r.passed
        ),
        "retest_finding_count": after_finding_count,
        "retest_finding_instance_count": after_finding_count,
        "resolved_finding_instance_count": getattr(rmeta, "resolved_finding_count", 0),
        "unresolved_finding_instance_count": after_finding_count,
        "patched_policy_effective": getattr(rmeta, "patched_policy_effective", False),
        "patched_system_prompt_effective": getattr(
            rmeta, "patched_system_prompt_effective", False
        ),
        "rejected_proposal_count": getattr(rmeta, "rejected_proposal_count", 0),
        "human_review_categories": list(report.human_review_requirements),
    }
    red_blue = ui_formatters.build_red_blue_dashboard_model(report)
    return {
        **summary_aliases,
        "readiness": ui_formatters.build_readiness_summary_model(report),
        "timeline": ui_formatters.build_demo_timeline_model(report),
        "red_blue": red_blue,
        "remediation": red_blue["blue"]["remediation"],
        "report_summary": ui_formatters.build_report_summary_model(report),
        "evidence": ui_formatters.build_evidence_report_model(report),
        "safeguards": ui_formatters.build_engineering_safeguards_model(),
        "agent_trace": trace,
        "execution_mode": trace["execution_mode"],
        "provider_type": trace["provider_type"],
        "schema_failure": schema_failure,
        "red_team_failure": red_team_failure,
        "semantic_judge_failure": semantic_judge_failure,
        "timeout_failure": timeout_failure,
        "tuning_fallback": tuning_fallback,
        "metadata": {
            "mode": effective_mode,
            "tuning_iterations": getattr(report.metadata, "tuning_iterations", 0),
            "max_tuning_iterations": MAX_TUNING_ITERATIONS,
            "evidence_basis": getattr(report.metadata, "evidence_basis", None),
            "patched_policy_effective": getattr(rmeta, "patched_policy_effective", False),
            "patched_system_prompt_effective": getattr(
                rmeta, "patched_system_prompt_effective", False
            ),
        },
        # Raw report (no API key) so the client can request a local audit export
        # without the server holding any per-session state.
        "report": report.model_dump(mode="json"),
    }


def run_assessment(req: RunAssessmentRequest):
    """Run a readiness assessment and return (report, response_dict).

    Deterministic mode requires no provider/credentials. Agent-assisted mode
    builds a provider from provider_config (validated, key used in memory only).
    Raises ApiError(400) on bad input/config. The api_key never appears in the
    returned response.
    """
    mode = req.mode or "deterministic"
    if mode not in ("deterministic", "agent_assisted"):
        raise ApiError(400, f"Unknown mode {mode!r}.")

    raw_policy = _parse_policy(req.security_policy_yaml)

    if mode == "deterministic":
        report = run_readiness_assessment(
            system_prompt=req.system_prompt,
            policy=raw_policy,
            business_context_text=req.business_context,
            mode="deterministic",
        )
        return report, build_assessment_response(report, mode="deterministic")

    # agent_assisted
    provider, models = build_provider(req.provider_config)
    timeout_config = TimeoutConfig.from_env()
    tuning_fallback_model = tuning_fallback_model_from_env()
    try:
        report = run_readiness_assessment(
            system_prompt=req.system_prompt,
            policy=raw_policy,
            business_context_text=req.business_context,
            mode="agent_assisted",
            provider=provider,
            timeout_config=timeout_config,
            tuning_fallback_model=tuning_fallback_model,
            provider_type=req.provider_config.provider_type,
            **models,
        )
    except RoleTimeoutError as exc:
        # A role TIMEOUT with no usable baseline evidence to preserve — return a
        # clean, role-tagged error (HTTP 504). Never echo the key/request body.
        raise _timeout_api_error(exc) from exc
    except RoleProviderError as exc:
        # A non-transient, role-attributed provider failure (e.g. auth) with no
        # baseline evidence to preserve.
        raise _role_provider_api_error(exc) from exc
    except ProviderError as exc:
        # Any other endpoint/network/provider failure — safe message (no key).
        raise ApiError(502, f"LLM provider error: {exc}") from exc
    return report, build_assessment_response(
        report, mode="agent_assisted", provider_config=req.provider_config
    )


def _timeout_diag_details(exc) -> dict:
    """Safe, structured role diagnostics for a timeout/provider error (no secrets)."""
    diag = exc.diagnostics()
    return {
        "failed_role": diag["failed_role"],
        "role_label": diag["role_label"],
        "failed_stage": diag["failed_role"],
        "provider": diag["provider_type"],
        "model": diag["model"],
        "timeout_seconds": diag["timeout_seconds"],
        "retry_count": diag["retry_count"],
        "message": diag["message"],
    }


def role_timeout_message(diag: dict) -> str:
    """Build the user-facing role-specific timeout message (no secrets)."""
    label = ROLE_LABEL.get(diag.get("failed_role"), "LLM Agent")
    model = diag.get("model") or "the configured model"
    retries = diag.get("retry_count", 0)
    return (
        f"LLM request timed out during {label} using {model} "
        f"(retried {retries} time(s))."
    )


def _timeout_api_error(exc: "RoleTimeoutError") -> "ApiError":
    diag = exc.diagnostics()
    return ApiError(
        504,
        role_timeout_message(diag),
        code="llm_timeout",
        details=_timeout_diag_details(exc),
    )


def _role_provider_api_error(exc: "RoleProviderError") -> "ApiError":
    diag = exc.diagnostics()
    label = diag["role_label"]
    return ApiError(
        502,
        f"LLM provider error during {label} using {diag.get('model')}.",
        code="llm_provider_error",
        details=_timeout_diag_details(exc),
    )


# --------------------------------------------------------------------------- #
# Provider connectivity test — validates the REAL per-role schema contracts the
# agents enforce (not just a generic JSON ping), so a "success" here predicts a
# real agent-assisted run.
# --------------------------------------------------------------------------- #
def _role_contract_check(provider, model, role, timeout):
    """Probe one role against its REAL agent schema under a SHORT timeout.

    Returns ``(ok, response_validated, message, debug_excerpt, error_type)`` where
    ``error_type`` is one of ``None`` (ok), ``"timeout"``, ``"schema"``, or
    ``"provider_error"`` — so the UI can report a TIMEOUT distinctly from a schema
    contract failure. The api_key is never echoed; excerpts are secret-redacted.
    """
    from .agents import ROLE_CONTRACTS
    from .errors import SchemaContractError
    from .json_contracts import load_validated_object, sanitize_excerpt

    contract = ROLE_CONTRACTS[role]
    try:
        raw = provider.complete(
            model=model,
            system_prompt=contract["system_prompt"],
            user_prompt=contract["test_instruction"],
            json_schema_instruction=f"Return a {contract['schema_name']} JSON object.",
            timeout=timeout,
        )
    except ProviderTimeoutError:
        return (
            False, False,
            f"Provider call for {role} timed out after {timeout:.0f}s.",
            None, "timeout",
        )
    except ProviderError as exc:
        return False, False, f"Provider call failed: {sanitize_excerpt(str(exc))}", None, "provider_error"
    except Exception:  # never leak internals
        return False, False, "Provider call failed: unexpected error.", None, "provider_error"

    try:
        load_validated_object(
            provider,
            model,
            raw,
            contract["schema"],
            contract["schema_name"],
            extra_check=contract["extra_check"],
            normalize=contract["normalize"],
        )
        return (
            True, True,
            f"Connected and returned a valid {role} schema contract.",
            None, None,
        )
    except ProviderTimeoutError:
        # The repair attempt timed out — report it as a timeout, not a schema fail.
        return (
            False, False,
            f"Provider call for {role} timed out after {timeout:.0f}s.",
            None, "timeout",
        )
    except SchemaContractError as exc:
        excerpt = getattr(exc, "raw_excerpt", None) or sanitize_excerpt(raw)
        return (
            False, False,
            f"Provider responded, but output did not satisfy the {role} schema contract.",
            excerpt, "schema",
        )
    except Exception:
        return (
            False, False,
            f"Provider responded, but output did not satisfy the {role} schema contract.",
            sanitize_excerpt(raw), "schema",
        )


def test_provider(provider_config, models_to_test=None) -> dict:
    """Validate one or more agent-role models against their REAL schema contracts.

    Proves the provider/model can produce output that satisfies the SAME Pydantic
    contracts the agents enforce — WITHOUT running an assessment, mutating any
    prompt/policy, or writing audit files. A per-role TIMEOUT is reported
    distinctly from a schema-contract failure (``error_type``), and each role
    carries its ``latency_ms``. The API key is used only in memory and never
    echoed, logged, or returned. Failures carry a short, secret-redacted
    ``debug_excerpt``.
    """
    roles = list(models_to_test) if models_to_test else list(AGENT_ROLES)
    unknown = [r for r in roles if r not in AGENT_ROLES]
    if unknown:
        raise ApiError(400, f"Unknown model roles: {', '.join(unknown)}.")
    if not roles:
        raise ApiError(400, "models_to_test must include at least one role.")

    # Builds the provider (raises ApiError(400) on missing key / invalid config).
    provider, models = build_provider(provider_config)
    provider_type = provider_config.provider_type
    # The connectivity probe uses the SHORT provider-test timeout (default 60s),
    # never the long agent timeouts — and fails FAST (no retry): a diagnostic must
    # tell the user quickly whether the provider works, not stall on backoff.
    test_timeout = TimeoutConfig.from_env().provider_test
    from .llm_runtime import RoleBoundProvider

    results = []
    overall_ok = True
    for role in roles:
        model = models[ROLE_MODEL_KEY[role]]
        probe_provider = RoleBoundProvider(
            provider,
            role="provider_test",
            provider_type=provider_type,
            timeout=test_timeout,
            max_retries=0,
            backoff_seconds=0.0,
        )
        start = time.perf_counter()
        ok, validated, message, excerpt, error_type = _role_contract_check(
            probe_provider, model, role, test_timeout
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        overall_ok = overall_ok and ok
        results.append(
            {
                "role": role,
                "purpose": ROLE_PURPOSE[role],
                "model": model,
                "ok": ok,
                "latency_ms": latency_ms,
                "response_validated": validated,
                "message": message,
                "debug_excerpt": excerpt,
                # Distinguishes a TIMEOUT from a schema-contract failure (or None).
                "error_type": error_type,
                "timed_out": error_type == "timeout",
            }
        )

    return {
        "ok": overall_ok,
        "provider_type": provider_type,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }


def audit_dir() -> Path:
    """Return the resolved audit directory (env NOXUS_AUDIT_DIR, default local)."""
    raw = os.environ.get("NOXUS_AUDIT_DIR") or DEFAULT_AUDIT_DIR
    return Path(raw).resolve()


def sanitize_audit_filename(name: Optional[str]) -> str:
    """Validate a client-suggested audit filename. Raises ApiError(400) if unsafe.

    Accepts a bare filename only — never a path. Rejects slashes, backslashes,
    ``..``, absolute paths, and control characters; enforces a ``.jsonl`` suffix.
    """
    if not name:
        return DEFAULT_AUDIT_FILENAME
    name = name.strip()
    if not name:
        return DEFAULT_AUDIT_FILENAME
    if (
        "/" in name
        or "\\" in name
        or ".." in name
        or name.startswith(".")
        or "\x00" in name
        or os.path.isabs(name)
        or name != os.path.basename(name)
    ):
        raise ApiError(400, "Invalid audit filename: provide a bare *.jsonl name.")
    if not name.endswith(".jsonl"):
        raise ApiError(400, "Audit filename must end with .jsonl.")
    return name


# Explicit, INTENTIONALLY STRICT allowlist of client-side routes that may
# receive the SPA shell (index.html). The React app navigates entirely by
# internal state (no react-router / URL routing), so the only true entry point
# is "/"; the remaining names are friendly deep-links that simply mirror the
# current nav section ids in apps/web/src/components/nav.ts (overview/target/
# assessment/results/evidence/risks/provider/proof) plus their hyphenated
# aliases. This list is deliberately NOT broadened to "any non-file path":
# ANY other path (e.g. /etc/passwd, /pyproject.toml, /src/..., /dashboard) must
# 404 instead of being treated as a client route — convenience never trumps
# security. If a new nav section is added, add its id here in lockstep.
FRONTEND_ROUTES = frozenset(
    {
        "",  # "/" — the SPA root
        # Canonical friendly route names.
        "overview",
        "target-config",
        "assessment",
        "results",
        "evidence",
        "open-risks",
        "provider-settings",
        "engineering-proof",
        # Internal nav section ids (kept in sync with apps/web/src/components/nav.ts).
        "target",
        "risks",
        "provider",
        "proof",
    }
)


def is_frontend_route(requested_path: str) -> bool:
    """True only for an allowlisted SPA client route (exact, single segment).

    A leading slash is tolerated; anything containing a further slash, a dot, a
    NUL, or a backslash is rejected outright (it is not a client route).
    """
    if requested_path is None:
        return False
    path = requested_path.lstrip("/")
    if "\x00" in path or "\\" in path or "/" in path or "." in path:
        return False
    return path in FRONTEND_ROUTES


def resolve_safe_static_path(static_root, requested_path: str) -> Optional[Path]:
    """Resolve a requested static path strictly inside ``static_root``.

    Returns the resolved Path when it is contained within ``static_root`` (it
    need not exist — the caller decides file-vs-SPA-fallback), or ``None`` when
    the request is absolute, contains a NUL, or escapes the root via traversal.
    Containment is verified after resolving symlinks/`..` with a commonpath check.
    """
    if requested_path.startswith("/") or "\x00" in requested_path or os.path.isabs(
        requested_path
    ):
        return None
    root = Path(static_root).resolve()
    candidate = (root / requested_path).resolve()
    try:
        if os.path.commonpath([str(root), str(candidate)]) != str(root):
            return None
    except ValueError:
        # Different drives / mixed absoluteness -> not contained.
        return None
    return candidate


def export_audit_local(report_dict: dict, filename: Optional[str] = None) -> str:
    """Validate a report dict and append it as one JSONL line under the audit dir.

    Opt-in only. The output location is ALWAYS the server-configured audit
    directory (``NOXUS_AUDIT_DIR``); the client may suggest a sanitized filename
    but never a path. Returns the resolved path as a string. The audit record is
    built from the report only and contains no API key.
    """
    from .audit_export import append_audit_jsonl
    from .schemas import ReadinessReport

    try:
        report = ReadinessReport.model_validate(report_dict)
    except Exception as exc:
        raise ApiError(400, f"Invalid report payload for audit export: {exc}") from exc

    safe_name = sanitize_audit_filename(filename)
    root = audit_dir()
    target = (root / safe_name).resolve()
    # Belt-and-suspenders containment check (filename is already sanitized).
    try:
        if os.path.commonpath([str(root), str(target)]) != str(root):
            raise ApiError(400, "Audit path escapes the configured audit directory.")
    except ValueError as exc:
        raise ApiError(400, "Invalid audit path.") from exc

    try:
        path = append_audit_jsonl(report, target)
    except OSError as exc:
        raise ApiError(500, f"Failed to write audit JSONL: {exc}") from exc
    return str(path)
