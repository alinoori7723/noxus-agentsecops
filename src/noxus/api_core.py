from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


PROVIDER_LOCAL = "local_openai_compatible"
PROVIDER_OPENAI = "openai_compatible"
PROVIDER_GEMINI = "gemini_native"
PROVIDER_TYPES = (PROVIDER_LOCAL, PROVIDER_OPENAI, PROVIDER_GEMINI)

DEFAULT_LOCAL_BASE_URL = "http://localhost:4000/v1"


DEFAULT_AUDIT_DIR = "outputs/audit"
DEFAULT_AUDIT_FILENAME = "readiness_reports.jsonl"


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


AGENT_ROLES = ("red", "judge", "tuning")
ROLE_MODEL_KEY = {"red": "red_model", "judge": "judge_model", "tuning": "tuning_model"}
ROLE_PURPOSE = {
    "red": "Generates adversarial probes",
    "judge": "Reviews semantic violations",
    "tuning": "Proposes schema-bound patches",
}


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        code: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.details = details or {}


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_type: str = PROVIDER_LOCAL
    base_url: str | None = None
    api_key: str | None = Field(default=None, repr=False)
    red_model: str | None = None
    judge_model: str | None = None
    tuning_model: str | None = None


class RunAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = "deterministic"
    system_prompt: str = ""
    security_policy_yaml: str = ""
    business_context: str = ""
    provider_config: ProviderConfig | None = None
    provider_profile: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class ProviderTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_config: ProviderConfig | None = None
    provider_profile: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")

    models_to_test: list[str] = Field(default_factory=lambda: list(AGENT_ROLES))


class AuditExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: dict
    filename: str | None = None


_REDACTED = "***REDACTED***"


def redact_provider_config(config: Any) -> dict:

    if config is None:
        return {}
    data = config.model_dump() if isinstance(config, BaseModel) else dict(config)
    if data.get("api_key"):
        data["api_key"] = _REDACTED
    return data


def redact_request(req: RunAssessmentRequest) -> dict:

    return {
        "mode": req.mode,
        "system_prompt_chars": len(req.system_prompt or ""),
        "security_policy_yaml_chars": len(req.security_policy_yaml or ""),
        "business_context_chars": len(req.business_context or ""),
        "provider_config": redact_provider_config(req.provider_config),
    }


def health_payload() -> dict:
    return {"ok": True, "product": PRODUCT_NAME, "mode": "api"}


def _read_sample(name: str) -> str:
    try:
        return (_SAMPLES / name).read_text(encoding="utf-8")
    except OSError:
        return ""


def sample_inputs() -> dict:

    return {
        "system_prompt": _read_sample("system_prompt.txt"),
        "security_policy_yaml": _read_sample("security_policy.yaml"),
        "business_context": _read_sample("support_case_base.md"),
    }


def proof_indicators(test_count: int | None = None) -> dict:

    return {
        "test_count": test_count,
        "max_tuning_iterations": MAX_TUNING_ITERATIONS,
        "schema_bound_agents": True,
        "deterministic_patch_engine": True,
        "local_jsonl_audit_export": True,
    }


POLICY_SCHEMA_MESSAGE = "Security Policy YAML does not match the supported Noxus policy schema."


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

    from .schemas import SecurityPolicy

    return list(SecurityPolicy.model_fields.keys())


def _policy_schema_error(raw: dict, exc: Exception) -> ApiError:

    allowed = supported_policy_keys()
    unsupported: list[str] = []

    errors = getattr(exc, "errors", None)
    if callable(errors):
        for e in errors():
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
        validate_policy(raw)
    except Exception as exc:
        raise _policy_schema_error(raw, exc) from exc
    return raw


BASE_URL_SCHEME_ERROR = "Base URL must include http:// or https://"


def _validate_base_url(base_url: str) -> None:

    from urllib.parse import urlparse

    parsed = urlparse((base_url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiError(400, BASE_URL_SCHEME_ERROR)


def build_provider(config: ProviderConfig | None) -> tuple[LLMProvider, dict]:

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
        else:
            if not config.base_url:
                raise ApiError(400, "openai_compatible provider requires a base_url.")
            _validate_base_url(config.base_url)
            provider = LiteLLMProvider(config.base_url, config.api_key)
    except ProviderError as exc:
        raise ApiError(400, f"Invalid provider configuration: {exc}") from exc

    models = {
        "red_model": config.red_model or DEFAULT_MODELS["red_model"],
        "judge_model": config.judge_model or DEFAULT_MODELS["judge_model"],
        "tuning_model": config.tuning_model or DEFAULT_MODELS["tuning_model"],
    }
    return provider, models


def _ev(maybe_enum) -> str:

    return getattr(maybe_enum, "value", None) or str(maybe_enum)


def _semantic_judgment_source(report) -> str:

    for results in (report.before_results, report.after_results):
        for r in results:
            for f in r.findings:
                if _ev(f.detection_mode) == "semantic_llm":
                    return "llm"
    return "deterministic"


def build_agent_trace(report, mode: str, provider_config) -> dict:

    is_agent = mode == "agent_assisted"
    pc = provider_config
    provider_type = pc.provider_type if (is_agent and pc is not None) else None

    def _model(role: str) -> str | None:
        if not is_agent:
            return None
        key = ROLE_MODEL_KEY[role]
        return (getattr(pc, key, None) if pc else None) or DEFAULT_MODELS[key]

    meta = report.metadata
    patch_count = len(report.patch_operations_applied)
    before_probes = len(report.before_results)
    baseline_finding_count = sum(len(r.findings) for r in report.before_results)
    semantic_source = _semantic_judgment_source(report)

    schema_failure = "schema_contract_failure" in list(report.human_review_requirements)
    failed_role = getattr(meta, "failed_role", None)

    red_team_status = getattr(meta, "red_team_status", None)
    continued_after_red = bool(getattr(meta, "continued_after_red_failure", False))
    fallback_used = getattr(meta, "fallback_used", None)
    fallback_reason = getattr(meta, "fallback_reason", None)

    timeout_role = getattr(meta, "timeout_failed_role", None)
    timeout_fatal = is_agent and bool(getattr(meta, "timeout_fatal", False))
    timeout_message = getattr(meta, "timeout_message", None)
    tuning_fallback_used = bool(getattr(meta, "tuning_fallback_used", False))
    tuning_fallback_model = getattr(meta, "tuning_fallback_model", None)

    red_failed = (
        is_agent
        and not timeout_fatal
        and (red_team_status == "failed" or (schema_failure and failed_role == "red"))
    )

    semantic_judge_status = getattr(meta, "semantic_judge_status", None)
    judge_degraded = is_agent and not red_failed and semantic_judge_status == "failed"
    evidence_basis = getattr(meta, "evidence_basis", None)

    _ROLE_ORDER = {"red": 0, "judge": 1, "tuning": 2}
    pipeline_failed = schema_failure or timeout_fatal

    failing_role = timeout_role if timeout_fatal else failed_role
    failed_idx = _ROLE_ORDER.get(failing_role or "unknown") if pipeline_failed else None

    def _agent_status(
        role: str, default_used: bool, default_not_used_summary: str, used_summary: str
    ) -> dict:
        idx = _ROLE_ORDER[role]
        if failed_idx is not None:
            if idx == failed_idx:
                if timeout_fatal:
                    return {
                        "source": "llm",
                        "status": "failed",
                        "summary": timeout_message or f"{used_summary.split('.')[0]} — timed out.",
                    }
                return {
                    "source": "llm",
                    "status": "failed",
                    "summary": f"{used_summary.split('.')[0]} — failed schema validation.",
                }
            if idx < failed_idx:
                return {"source": "llm", "status": "used", "summary": used_summary}
            return {
                "source": "llm",
                "status": "not_used",
                "summary": "Not reached — an earlier agent stage failed.",
            }
        return {
            "source": "llm",
            "status": "used" if default_used else "not_used",
            "summary": used_summary if default_used else default_not_used_summary,
        }

    if red_failed:
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
                tuning = {"source": "llm", "status": "not_used", "summary": "Proposed no patches."}
        else:
            judge = {
                "source": "llm",
                "status": "not_used",
                "summary": "Not reached — the Red Team Agent failed and no "
                "deterministic baseline fallback was available.",
            }
            tuning = {
                "source": "llm",
                "status": "not_used",
                "summary": "Not reached — the Red Team Agent failed and no "
                "deterministic baseline fallback was available.",
            }
    elif is_agent:
        red = _agent_status(
            "red",
            True,
            "Red team did not run.",
            "Generated structured probes on top of the deterministic baseline.",
        )

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
                "judge",
                semantic_source == "llm",
                "Ran, but added no semantic findings beyond deterministic checks.",
                "Evaluated semantic violations and added judged findings.",
            )

        tuning = _agent_status(
            "tuning",
            patch_count > 0,
            "Proposed no patches.",
            f"Proposed a schema-bound PatchSet ({patch_count} operations).",
        )

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
        judge = {
            "source": "deterministic",
            "status": "not_used",
            "summary": "Semantic judge is not used in deterministic mode.",
        }
        tuning = {
            "source": "deterministic_mapper",
            "status": "used" if patch_count else "not_used",
            "summary": f"Patches mapped deterministically from findings ({patch_count}).",
        }

    stages = [
        {
            "stage": "red_team",
            "role": "red",
            "model": _model("red"),
            "provider_type": provider_type,
            **red,
        },
        {
            "stage": "semantic_judge",
            "role": "judge",
            "model": _model("judge"),
            "provider_type": provider_type,
            **judge,
        },
        {
            "stage": "policy_tuning",
            "role": "tuning",
            "model": _model("tuning"),
            "provider_type": provider_type,
            **tuning,
        },
        {
            "stage": "patch_application",
            "role": None,
            "model": None,
            "provider_type": None,
            "source": "deterministic_engine",
            "status": "used" if patch_count else "not_used",
            "summary": f"Deterministic engine applied {patch_count} allowed patch operations.",
        },
    ]
    return {
        "execution_mode": mode,
        "provider_type": provider_type,
        "red_model": _model("red"),
        "judge_model": _model("judge"),
        "tuning_model": _model("tuning"),
        "semantic_judgment_source": semantic_source,
        "patch_proposal_source": "llm" if is_agent else "deterministic_mapper",
        "fallback_used": fallback_used if red_failed else None,
        "fallback_reason": fallback_reason if red_failed else None,
        "continued_after_red_failure": continued_after_red,
        "baseline_probe_count": before_probes,
        "baseline_finding_count": baseline_finding_count,
        "evidence_basis": evidence_basis,
        "semantic_judge_status": semantic_judge_status,
        "timeout_failed_role": timeout_role,
        "timeout_fatal": timeout_fatal,
        "tuning_fallback_used": tuning_fallback_used,
        "tuning_fallback_model": tuning_fallback_model if tuning_fallback_used else None,
        "stages": stages,
    }


def build_assessment_response(report, *, mode=None, provider_config=None) -> dict:

    effective_mode = mode or getattr(report.metadata, "mode", "deterministic")
    trace = build_agent_trace(report, effective_mode, provider_config)
    meta = report.metadata
    baseline_findings = sum(len(r.findings) for r in report.before_results)
    schema_failure = None
    if "schema_contract_failure" in list(report.human_review_requirements):
        schema_failure = {
            "failed_stage": getattr(meta, "failed_stage", None),
            "failed_role": getattr(meta, "failed_role", None),
            "debug_excerpt": getattr(meta, "schema_failure_excerpt", None),
            "baseline_preserved": bool(report.before_results),
            "baseline_probe_count": len(report.before_results),
            "baseline_finding_count": baseline_findings,
            "reason": "schema contract failure",
        }

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
            "debug_excerpt": getattr(meta, "red_team_failure_excerpt", None),
        }

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
            "debug_excerpt": getattr(meta, "semantic_judge_failure_excerpt", None),
        }

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

    tuning_fallback = None
    if getattr(meta, "tuning_fallback_used", False):
        tuning_fallback = {
            "used": True,
            "original_model": getattr(meta, "tuning_fallback_original_model", None),
            "fallback_model": getattr(meta, "tuning_fallback_model", None),
            "reason": getattr(meta, "tuning_fallback_reason", None),
        }

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
        "failed_stage": getattr(rmeta, "failed_stage", None),
        "failed_role": getattr(rmeta, "failed_role", None),
        "resolved_probe_count": getattr(rmeta, "resolved_probe_count", 0),
        "unresolved_probe_count": getattr(rmeta, "unresolved_probe_count", 0),
        "resolved_finding_count": getattr(rmeta, "resolved_finding_count", 0),
        "unresolved_finding_count": getattr(rmeta, "unresolved_finding_count", 0),
        "baseline_probe_count": len(report.before_results),
        "baseline_failed_probe_count": sum(1 for r in report.before_results if not r.passed),
        "baseline_finding_count": baseline_findings,
        "baseline_finding_instance_count": baseline_findings,
        "retest_failed_probe_count": sum(1 for r in report.after_results if not r.passed),
        "retest_finding_count": after_finding_count,
        "retest_finding_instance_count": after_finding_count,
        "resolved_finding_instance_count": getattr(rmeta, "resolved_finding_count", 0),
        "unresolved_finding_instance_count": after_finding_count,
        "patched_policy_effective": getattr(rmeta, "patched_policy_effective", False),
        "patched_system_prompt_effective": getattr(rmeta, "patched_system_prompt_effective", False),
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
        "report": report.model_dump(mode="json"),
    }


def run_assessment(req: RunAssessmentRequest):

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

    if req.provider_config is None:
        raise ApiError(400, "Agent-Assisted Mode requires provider_config.")
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
        raise _timeout_api_error(exc) from exc
    except RoleProviderError as exc:
        raise _role_provider_api_error(exc) from exc
    except ProviderError as exc:
        raise ApiError(502, f"LLM provider error: {exc}") from exc
    return report, build_assessment_response(
        report, mode="agent_assisted", provider_config=req.provider_config
    )


def _timeout_diag_details(exc) -> dict:

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

    label = ROLE_LABEL.get(diag.get("failed_role") or "unknown", "LLM Agent")
    model = diag.get("model") or "the configured model"
    retries = diag.get("retry_count", 0)
    return f"LLM request timed out during {label} using {model} (retried {retries} time(s))."


def _timeout_api_error(exc: RoleTimeoutError) -> ApiError:
    diag = exc.diagnostics()
    return ApiError(
        504,
        role_timeout_message(diag),
        code="llm_timeout",
        details=_timeout_diag_details(exc),
    )


def _role_provider_api_error(exc: RoleProviderError) -> ApiError:
    diag = exc.diagnostics()
    label = diag["role_label"]
    return ApiError(
        502,
        f"LLM provider error during {label} using {diag.get('model')}.",
        code="llm_provider_error",
        details=_timeout_diag_details(exc),
    )


def _role_contract_check(provider, model, role, timeout):

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
            False,
            False,
            f"Provider call for {role} timed out after {timeout:.0f}s.",
            None,
            "timeout",
        )
    except ProviderError as exc:
        return (
            False,
            False,
            f"Provider call failed: {sanitize_excerpt(str(exc))}",
            None,
            "provider_error",
        )
    except Exception:
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
            True,
            True,
            f"Connected and returned a valid {role} schema contract.",
            None,
            None,
        )
    except ProviderTimeoutError:
        return (
            False,
            False,
            f"Provider call for {role} timed out after {timeout:.0f}s.",
            None,
            "timeout",
        )
    except SchemaContractError as exc:
        excerpt = getattr(exc, "raw_excerpt", None) or sanitize_excerpt(raw)
        return (
            False,
            False,
            f"Provider responded, but output did not satisfy the {role} schema contract.",
            excerpt,
            "schema",
        )
    except Exception:
        return (
            False,
            False,
            f"Provider responded, but output did not satisfy the {role} schema contract.",
            sanitize_excerpt(raw),
            "schema",
        )


def test_provider(provider_config, models_to_test=None) -> dict:

    roles = list(models_to_test) if models_to_test else list(AGENT_ROLES)
    unknown = [r for r in roles if r not in AGENT_ROLES]
    if unknown:
        raise ApiError(400, f"Unknown model roles: {', '.join(unknown)}.")
    if not roles:
        raise ApiError(400, "models_to_test must include at least one role.")

    provider, models = build_provider(provider_config)
    provider_type = provider_config.provider_type

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
                "error_type": error_type,
                "timed_out": error_type == "timeout",
            }
        )

    return {
        "ok": overall_ok,
        "provider_type": provider_type,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "results": results,
    }


def audit_dir() -> Path:

    raw = os.environ.get("NOXUS_AUDIT_DIR") or DEFAULT_AUDIT_DIR
    return Path(raw).resolve()


def sanitize_audit_filename(name: str | None) -> str:

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


FRONTEND_ROUTES = frozenset(
    {
        "",
        "overview",
        "target-config",
        "assessment",
        "results",
        "evidence",
        "open-risks",
        "provider-settings",
        "engineering-proof",
        "target",
        "risks",
        "provider",
        "proof",
    }
)


def is_frontend_route(requested_path: str) -> bool:

    if requested_path is None:
        return False
    path = requested_path.lstrip("/")
    if "\x00" in path or "\\" in path or "/" in path or "." in path:
        return False
    return path in FRONTEND_ROUTES


def resolve_safe_static_path(static_root, requested_path: str) -> Path | None:

    if requested_path.startswith("/") or "\x00" in requested_path or os.path.isabs(requested_path):
        return None
    root = Path(static_root).resolve()
    candidate = (root / requested_path).resolve()
    try:
        if os.path.commonpath([str(root), str(candidate)]) != str(root):
            return None
    except ValueError:
        return None
    return candidate


def export_audit_local(report_dict: dict, filename: str | None = None) -> str:

    from .audit_export import append_audit_jsonl
    from .schemas import ReadinessReport

    try:
        report = ReadinessReport.model_validate(report_dict)
    except Exception as exc:
        raise ApiError(400, f"Invalid report payload for audit export: {exc}") from exc

    safe_name = sanitize_audit_filename(filename)
    root = audit_dir()
    target = (root / safe_name).resolve()

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
