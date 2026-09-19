from __future__ import annotations

import os
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .json_contracts import sanitize_excerpt
from .llm_provider import (
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderNetworkError,
    ProviderTimeoutError,
)

DEFAULT_LLM_TIMEOUT_SECONDS = 180.0
DEFAULT_TUNING_TIMEOUT_SECONDS = 240.0
DEFAULT_PROVIDER_TEST_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 1.5


ROLE_RED = "red"
ROLE_JUDGE = "judge"
ROLE_TUNING = "tuning"
ROLE_PROVIDER_TEST = "provider_test"
ROLE_UNKNOWN = "unknown"


ROLE_LABEL = {
    ROLE_RED: "Red Team Agent",
    ROLE_JUDGE: "Semantic Judge Agent",
    ROLE_TUNING: "Policy Tuning Agent",
    ROLE_PROVIDER_TEST: "Provider Diagnostics",
    ROLE_UNKNOWN: "LLM Agent",
}


class RoleProviderError(ProviderError):
    def __init__(
        self,
        *,
        role: str,
        model: str | None,
        provider_type: str | None,
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

        self.safe_message = message

    def diagnostics(self) -> dict:

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
    pass


def _env_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class TimeoutConfig:
    red: float = DEFAULT_LLM_TIMEOUT_SECONDS
    judge: float = DEFAULT_LLM_TIMEOUT_SECONDS
    tuning: float = DEFAULT_TUNING_TIMEOUT_SECONDS
    provider_test: float = DEFAULT_PROVIDER_TEST_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> TimeoutConfig:

        env = os.environ if env is None else env
        global_timeout = _env_float(env, "NOXUS_LLM_TIMEOUT_SECONDS", DEFAULT_LLM_TIMEOUT_SECONDS)
        return cls(
            red=_env_float(env, "NOXUS_RED_TIMEOUT_SECONDS", global_timeout),
            judge=_env_float(env, "NOXUS_JUDGE_TIMEOUT_SECONDS", global_timeout),
            tuning=_env_float(env, "NOXUS_TUNING_TIMEOUT_SECONDS", DEFAULT_TUNING_TIMEOUT_SECONDS),
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


def tuning_fallback_model_from_env(env: Mapping[str, str] | None = None) -> str | None:

    env = os.environ if env is None else env
    raw = (env.get("NOXUS_TUNING_FALLBACK_MODEL") or "").strip()
    return raw or None


class RoleBoundProvider:
    def __init__(
        self,
        inner: LLMProvider,
        *,
        role: str,
        provider_type: str | None,
        timeout: float,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float], float] | None = None,
    ) -> None:
        self.inner = inner
        self.role = role
        self.provider_type = provider_type
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self._sleep = sleep

        self._jitter = (
            jitter
            if jitter is not None
            else (lambda base: random.uniform(0.0, base * 0.25) if base > 0 else 0.0)
        )

        self.retry_count = 0

    def _backoff_delay(self, attempt: int) -> float:

        base = self.backoff_seconds * (2**attempt)
        return base + self._jitter(base)

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema_instruction: str | None = None,
        timeout: float | None = None,
    ) -> str:
        last_exc: ProviderError | None = None
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
                last_exc = exc
                if attempt < self.max_retries:
                    self.retry_count += 1
                    delay = self._backoff_delay(attempt)
                    if delay > 0:
                        self._sleep(delay)
                    continue
                break
            except ProviderAuthError as exc:
                raise RoleProviderError(
                    role=self.role,
                    model=model,
                    provider_type=self.provider_type,
                    timeout_seconds=self.timeout,
                    retry_count=self.retry_count,
                    message=sanitize_excerpt(str(exc)),
                ) from exc
            except ProviderError as exc:
                raise RoleProviderError(
                    role=self.role,
                    model=model,
                    provider_type=self.provider_type,
                    timeout_seconds=self.timeout,
                    retry_count=self.retry_count,
                    message=sanitize_excerpt(str(exc)),
                ) from exc

        raise RoleTimeoutError(
            role=self.role,
            model=model,
            provider_type=self.provider_type,
            timeout_seconds=self.timeout,
            retry_count=self.retry_count,
            message=sanitize_excerpt(str(last_exc) if last_exc else "LLM request timed out."),
        )
