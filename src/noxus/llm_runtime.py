"""Role-aware LLM runtime: per-role timeouts, bounded retry/backoff, and
role-tagged diagnostics — standard library only (no SDKs, no new deps).

The live demo failure mode is a slow/unstable provider (LiteLLM/Gemini) that
times out, surfacing a generic "LLM request timed out." with no context. This
module wraps any ``LLMProvider`` so that EVERY call made for a given agent role
(red / judge / tuning / provider_test):

* uses that role's configured timeout (env-tunable),
* retries a TRANSIENT timeout/network error a bounded number of times with
  exponential backoff + small jitter (never retries auth or schema errors),
* counts retries, and
* on final failure raises a ``RoleTimeoutError`` / ``RoleProviderError`` that
  carries the role, model, provider type, timeout, retry count, and a
  secret-redacted message — so the UI can say exactly which agent timed out.

No API key, request body, or Authorization header is ever stored or logged here.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .json_contracts import sanitize_excerpt
from .llm_provider import (
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderNetworkError,
    ProviderTimeoutError,
)

# Defaults are intentionally generous: real Gemini Pro tuning calls can take
# minutes under load. They are env-overridable so a demo host can tune them.
DEFAULT_LLM_TIMEOUT_SECONDS = 180.0
DEFAULT_TUNING_TIMEOUT_SECONDS = 240.0
DEFAULT_PROVIDER_TEST_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 1.5

# The roles a timeout can be attributed to (mirrors the agent pipeline + the
# connectivity probe). "unknown" is the safe fallback when a role is absent.
ROLE_RED = "red"
ROLE_JUDGE = "judge"
ROLE_TUNING = "tuning"
ROLE_PROVIDER_TEST = "provider_test"
ROLE_UNKNOWN = "unknown"

# Human-readable role label used in user-facing timeout messages.
ROLE_LABEL = {
    ROLE_RED: "Red Team Agent",
    ROLE_JUDGE: "Semantic Judge Agent",
    ROLE_TUNING: "Policy Tuning Agent",
    ROLE_PROVIDER_TEST: "Provider Diagnostics",
    ROLE_UNKNOWN: "LLM Agent",
}


class RoleProviderError(ProviderError):
    """A NON-transient provider failure attributed to a specific agent role.

    Carries safe, structured diagnostics (role / model / provider_type /
    timeout_seconds / retry_count / sanitized message). Never holds an API key.
    """

    def __init__(
        self,
        *,
        role: str,
        model: Optional[str],
        provider_type: Optional[str],
        timeout_seconds: float,
        retry_count: int,
        message: str,
    ) -> None:
        super().__init__(message)
        self.role = role
        self.model = model
        self.provider_type = provider_type
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count
        # Pre-sanitized, user-safe message (no key, no request body).
        self.safe_message = message

    def diagnostics(self) -> dict:
        """Return a safe, structured diagnostics dict (no secrets)."""
        return {
            "failed_role": self.role,
            "role_label": ROLE_LABEL.get(self.role, ROLE_LABEL[ROLE_UNKNOWN]),
            "model": self.model,
            "provider_type": self.provider_type,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "message": self.safe_message,
            "is_timeout": isinstance(self, RoleTimeoutError),
        }


class RoleTimeoutError(RoleProviderError, ProviderTimeoutError):
    """A role-attributed TIMEOUT after the configured retries were exhausted.

    Subclasses ``ProviderTimeoutError`` so a timed-out repair attempt inside
    json_contracts is re-raised as a timeout (never mislabeled a schema failure).
    """


def _env_float(env: dict, key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(env: dict, key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class TimeoutConfig:
    """Per-role timeout + retry/backoff configuration (env-driven, with defaults)."""

    red: float = DEFAULT_LLM_TIMEOUT_SECONDS
    judge: float = DEFAULT_LLM_TIMEOUT_SECONDS
    tuning: float = DEFAULT_TUNING_TIMEOUT_SECONDS
    provider_test: float = DEFAULT_PROVIDER_TEST_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "TimeoutConfig":
        """Build a config from environment variables.

        ``NOXUS_LLM_TIMEOUT_SECONDS`` is the global default (180). Red and Judge
        INHERIT it unless their own override is set; Tuning defaults to 240 and
        the provider-test probe to 60 — both independently overridable.
        """
        env = os.environ if env is None else env
        global_timeout = _env_float(
            env, "NOXUS_LLM_TIMEOUT_SECONDS", DEFAULT_LLM_TIMEOUT_SECONDS
        )
        return cls(
            red=_env_float(env, "NOXUS_RED_TIMEOUT_SECONDS", global_timeout),
            judge=_env_float(env, "NOXUS_JUDGE_TIMEOUT_SECONDS", global_timeout),
            tuning=_env_float(
                env, "NOXUS_TUNING_TIMEOUT_SECONDS", DEFAULT_TUNING_TIMEOUT_SECONDS
            ),
            provider_test=_env_float(
                env,
                "NOXUS_PROVIDER_TEST_TIMEOUT_SECONDS",
                DEFAULT_PROVIDER_TEST_TIMEOUT_SECONDS,
            ),
            max_retries=_env_int(env, "NOXUS_LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES),
            backoff_seconds=_env_float(
                env, "NOXUS_LLM_RETRY_BACKOFF_SECONDS", DEFAULT_RETRY_BACKOFF_SECONDS
            ),
        )

    def timeout_for(self, role: str) -> float:
        return {
            ROLE_RED: self.red,
            ROLE_JUDGE: self.judge,
            ROLE_TUNING: self.tuning,
            ROLE_PROVIDER_TEST: self.provider_test,
        }.get(role, self.red)


def tuning_fallback_model_from_env(env: Optional[dict] = None) -> Optional[str]:
    """Optional fallback tuning model (``NOXUS_TUNING_FALLBACK_MODEL``)."""
    env = os.environ if env is None else env
    raw = (env.get("NOXUS_TUNING_FALLBACK_MODEL") or "").strip()
    return raw or None


class RoleBoundProvider:
    """Wraps an ``LLMProvider`` so all calls for one role get that role's timeout,
    bounded transient-retry with backoff, and role-tagged failure diagnostics.

    Implements the ``LLMProvider`` ``complete`` protocol, so existing agents and
    the json_contracts repair path use it unchanged. The caller-supplied
    ``timeout`` argument is intentionally ignored — the ROLE timeout always wins.
    """

    def __init__(
        self,
        inner: LLMProvider,
        *,
        role: str,
        provider_type: Optional[str],
        timeout: float,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Optional[Callable[[float], float]] = None,
    ) -> None:
        self.inner = inner
        self.role = role
        self.provider_type = provider_type
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self._sleep = sleep
        # Default jitter is a small non-negative perturbation; injectable for tests.
        self._jitter = jitter if jitter is not None else (
            lambda base: random.uniform(0.0, base * 0.25) if base > 0 else 0.0
        )
        # Cumulative transient retries across every call made for this role
        # (primary + any repair attempt). Surfaced in diagnostics.
        self.retry_count = 0

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff (base * 2**attempt) plus a small jitter."""
        base = self.backoff_seconds * (2 ** attempt)
        return base + self._jitter(base)

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema_instruction: Optional[str] = None,
        timeout: Optional[float] = None,  # ignored — the role timeout wins
    ) -> str:
        last_exc: Optional[ProviderError] = None
        for attempt in range(self.max_retries + 1):
            try:
                return self.inner.complete(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    json_schema_instruction=json_schema_instruction,
                    timeout=self.timeout,
                )
            except (ProviderTimeoutError, ProviderNetworkError) as exc:
                # TRANSIENT — retry with backoff up to the configured limit.
                last_exc = exc
                if attempt < self.max_retries:
                    self.retry_count += 1
                    delay = self._backoff_delay(attempt)
                    if delay > 0:
                        self._sleep(delay)
                    continue
                break
            except ProviderAuthError as exc:
                # NON-transient — never retry an auth failure.
                raise RoleProviderError(
                    role=self.role,
                    model=model,
                    provider_type=self.provider_type,
                    timeout_seconds=self.timeout,
                    retry_count=self.retry_count,
                    message=sanitize_excerpt(str(exc)),
                ) from exc
            except ProviderError as exc:
                # Other provider errors (non-timeout HTTP, malformed body) —
                # not safe to retry blindly; surface with role context.
                raise RoleProviderError(
                    role=self.role,
                    model=model,
                    provider_type=self.provider_type,
                    timeout_seconds=self.timeout,
                    retry_count=self.retry_count,
                    message=sanitize_excerpt(str(exc)),
                ) from exc

        # Retries exhausted on a transient timeout/network error.
        raise RoleTimeoutError(
            role=self.role,
            model=model,
            provider_type=self.provider_type,
            timeout_seconds=self.timeout,
            retry_count=self.retry_count,
            message=sanitize_excerpt(str(last_exc) if last_exc else "LLM request timed out."),
        )
