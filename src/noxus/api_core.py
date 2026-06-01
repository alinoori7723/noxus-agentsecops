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

# Provider connectivity probe: a tiny structured-JSON round-trip that proves a
# real model/API call happened, without running an assessment or mutating state.
PROVIDER_TEST_TIMEOUT = 12.0
_PROBE_SYSTEM = (
    "You are a connectivity probe for a security tool. Reply with ONLY a single "
    "compact JSON object and nothing else."
)
_PROBE_USER = 'Return exactly this JSON object: {"noxus_provider_check": true}'
_PROBE_SCHEMA = (
    'Output must be exactly one JSON object: {"noxus_provider_check": true}. '
    "No prose, no markdown, no code fences."
)


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

    patch_count = len(report.patch_operations_applied)
    before_probes = len(report.before_results)
    semantic_source = _semantic_judgment_source(report)
    # A schema-contract abort (not just a high-severity finding) is the only case
    # where the agent pipeline itself failed and routed to human review.
    schema_failure = "schema_contract_failure" in list(report.human_review_requirements)

    # Red Team
    if is_agent:
        red = {
            "source": "llm",
            "status": "human_review_required" if schema_failure else "used",
            "summary": "Generated structured probes on top of the deterministic baseline.",
        }
    else:
        red = {
            "source": "deterministic_baseline",
            "status": "used",
            "summary": f"Ran {before_probes} deterministic baseline probes.",
        }

    # Semantic Judge
    if is_agent and schema_failure:
        judge = {"source": "llm", "status": "human_review_required",
                 "summary": "Schema-bound judgment aborted; routed to human review."}
    elif is_agent and semantic_source == "llm":
        judge = {"source": "llm", "status": "used",
                 "summary": "Evaluated semantic violations and added judged findings."}
    elif is_agent:
        judge = {"source": "llm", "status": "not_used",
                 "summary": "Ran, but added no semantic findings beyond deterministic checks."}
    else:
        judge = {"source": "deterministic", "status": "not_used",
                 "summary": "Semantic judge is not used in deterministic mode."}

    # Policy Tuning (proposes the patch set)
    if is_agent and schema_failure:
        tuning = {"source": "llm", "status": "human_review_required",
                  "summary": "Patch proposal aborted on a schema-contract failure."}
    elif is_agent:
        tuning = {"source": "llm",
                  "status": "used" if patch_count else "not_used",
                  "summary": f"Proposed a schema-bound PatchSet ({patch_count} operations)."}
    else:
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
    return {
        "readiness": ui_formatters.build_readiness_summary_model(report),
        "timeline": ui_formatters.build_demo_timeline_model(report),
        "red_blue": ui_formatters.build_red_blue_dashboard_model(report),
        "evidence": ui_formatters.build_evidence_report_model(report),
        "safeguards": ui_formatters.build_engineering_safeguards_model(),
        "agent_trace": trace,
        "execution_mode": trace["execution_mode"],
        "provider_type": trace["provider_type"],
        "metadata": {
            "mode": effective_mode,
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
        return report, build_assessment_response(report, mode="deterministic")

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
    return report, build_assessment_response(
        report, mode="agent_assisted", provider_config=req.provider_config
    )


# --------------------------------------------------------------------------- #
# Provider connectivity test (proves a real model/API call; runs no assessment)
# --------------------------------------------------------------------------- #
def _validate_probe_response(text: str) -> bool:
    """True iff the model returned a parseable JSON object (markdown-fence tolerant)."""
    if not text:
        return False
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t[:4].lower() == "json":
            t = t[4:].strip()
    try:
        return isinstance(json.loads(t), dict)
    except (json.JSONDecodeError, ValueError):
        return False


def test_provider(provider_config, models_to_test=None) -> dict:
    """Probe one or more agent-role models with a tiny structured-JSON call.

    Proves connectivity + a valid structured response WITHOUT running an
    assessment, mutating any prompt/policy, or writing audit files. The API key
    is used only in memory and never echoed, logged, or returned.
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

    results = []
    overall_ok = True
    for role in roles:
        model = models[ROLE_MODEL_KEY[role]]
        start = time.perf_counter()
        ok = False
        validated = False
        message = ""
        try:
            text = provider.complete(
                model=model,
                system_prompt=_PROBE_SYSTEM,
                user_prompt=_PROBE_USER,
                json_schema_instruction=_PROBE_SCHEMA,
                timeout=PROVIDER_TEST_TIMEOUT,
            )
            validated = _validate_probe_response(text)
            ok = validated
            message = (
                "Connected and returned a valid structured response."
                if validated
                else "Connected, but the model did not return valid structured JSON."
            )
        except ProviderError as exc:
            # ProviderError messages are built from non-secret fields only.
            message = f"Provider call failed: {exc}"
        except Exception:  # never leak internals (could contain request detail)
            message = "Provider call failed: unexpected error."
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
