"""Pure-Python API core for the Noxus AgentSecOps web UI.

This module contains NO web-framework imports. It is the testable seam between
the React frontend's HTTP contract and the accepted Noxus orchestrator. The thin
``api_server`` module wraps these functions with HTTP routes and static serving.

Honest-labeling, scoring, evaluator, agent, and patch behavior all live in the
unchanged core; this module only adapts inputs/outputs. Provider API keys are
used in memory for a single request and are never logged, returned, or persisted.
"""

from __future__ import annotations

import os
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


class ApiError(Exception):
    """A request-level error carrying a safe HTTP status code and message.

    The ``message`` is guaranteed safe to return to the client: it never
    contains the caller's API key (provider construction errors are rephrased).
    """

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


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
        "business_context": _read_sample("business_context.md"),
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


def _parse_policy(security_policy_yaml: str) -> dict:
    try:
        raw = yaml.safe_load(security_policy_yaml) or {}
    except yaml.YAMLError as exc:
        raise ApiError(400, f"Invalid security policy YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ApiError(400, "Security policy must be a YAML mapping.")
    try:
        validate_policy(raw)  # raise early on a malformed policy
    except Exception as exc:  # pydantic ValidationError -> safe 400
        raise ApiError(400, f"Security policy failed validation: {exc}") from exc
    return raw


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
            provider = LiteLLMProvider(
                config.base_url or DEFAULT_LOCAL_BASE_URL, config.api_key
            )
        else:  # PROVIDER_OPENAI
            if not config.base_url:
                raise ApiError(
                    400, "openai_compatible provider requires a base_url."
                )
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


def build_assessment_response(report) -> dict:
    """Assemble the full UI display payload from a ReadinessReport.

    Reuses the pure-Python ui_formatters so all honest-labeling rules
    (CONDITIONAL_PASS, [DETERMINISTIC SIMULATION], [SEMANTIC LLM JUDGMENT],
    real [CRITICAL_SAFETY_RAILS] telemetry, visible open risks) are applied in
    exactly one place. Contains no API key.
    """
    return {
        "readiness": ui_formatters.build_readiness_summary_model(report),
        "timeline": ui_formatters.build_demo_timeline_model(report),
        "red_blue": ui_formatters.build_red_blue_dashboard_model(report),
        "evidence": ui_formatters.build_evidence_report_model(report),
        "safeguards": ui_formatters.build_engineering_safeguards_model(),
        "metadata": {
            "mode": getattr(report.metadata, "mode", "deterministic"),
            "tuning_iterations": getattr(report.metadata, "tuning_iterations", 0),
            "max_tuning_iterations": MAX_TUNING_ITERATIONS,
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
        return report, build_assessment_response(report)

    # agent_assisted
    provider, models = build_provider(req.provider_config)
    try:
        report = run_readiness_assessment(
            system_prompt=req.system_prompt,
            policy=raw_policy,
            business_context_text=req.business_context,
            mode="agent_assisted",
            provider=provider,
            **models,
        )
    except ProviderError as exc:
        # Endpoint/network/provider failure — surface a safe message (no key).
        raise ApiError(502, f"LLM provider error: {exc}") from exc
    return report, build_assessment_response(report)


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
