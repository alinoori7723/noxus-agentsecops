"""LLM provider abstraction for local LiteLLM-compatible usage.

Milestone 2 uses ONLY the Python standard library for HTTP (urllib). No official
provider SDKs, no requests/httpx, no cloud clients. The default provider speaks
the OpenAI-style ``/v1/chat/completions`` wire format exposed by a local
LiteLLM gateway.

Tests must never make real network calls — they use FakeLLMProvider instead.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Optional, Protocol, runtime_checkable

DEFAULT_TIMEOUT = 30.0


class ProviderError(Exception):
    """Raised when an LLM provider fails to return a usable response."""


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal schema-agnostic provider interface.

    Implementations return the raw text content of the model's reply. They do
    NOT parse or validate JSON — that is the job of json_contracts.
    """

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema_instruction: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> str:
        ...


class LiteLLMProvider:
    """OpenAI-style chat-completions client backed by urllib only."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not base_url:
            raise ProviderError("LiteLLMProvider requires a non-empty base_url.")
        if not api_key:
            raise ProviderError("LiteLLMProvider requires a non-empty api_key.")
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout

    def _endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            return base + "/chat/completions"
        return base + "/v1/chat/completions"

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema_instruction: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> str:
        system_content = system_prompt
        if json_schema_instruction:
            system_content = f"{system_prompt}\n\n{json_schema_instruction}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint(),
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        effective_timeout = self.timeout if timeout is None else timeout
        try:
            with urllib.request.urlopen(request, timeout=effective_timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"HTTP error from LLM endpoint: {exc.code} {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Network error contacting LLM endpoint: {exc.reason}") from exc
        except socket.timeout as exc:
            raise ProviderError("LLM request timed out.") from exc

        try:
            parsed = json.loads(body)
            return parsed["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Malformed response from LLM endpoint: {exc}") from exc


class FakeLLMProvider:
    """Deterministic in-memory provider for tests (no network).

    Responses are routed by a tag embedded in each agent's system prompt
    (``[NOXUS_RED_TEAM]``, ``[NOXUS_JUDGE]``, ``[NOXUS_TUNING]``,
    ``[NOXUS_REPAIR]``), or served from a FIFO ``queue`` when provided. Every
    call is recorded in ``self.calls`` for assertion in tests.
    """

    RED_TAG = "[NOXUS_RED_TEAM]"
    JUDGE_TAG = "[NOXUS_JUDGE]"
    TUNING_TAG = "[NOXUS_TUNING]"
    REPAIR_TAG = "[NOXUS_REPAIR]"

    def __init__(
        self,
        *,
        red: Optional[str] = None,
        judge: Optional[str] = None,
        tuning: Optional[str] = None,
        repair: Optional[str] = None,
        default: Optional[str] = None,
        queue: Optional[list[str]] = None,
    ) -> None:
        self.red = red
        self.judge = judge
        self.tuning = tuning
        self.repair = repair
        self.default = default
        self.queue = list(queue) if queue is not None else None
        self.calls: list[dict] = []

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema_instruction: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "json_schema_instruction": json_schema_instruction,
            }
        )

        if self.queue is not None:
            if not self.queue:
                raise ProviderError("FakeLLMProvider: queue exhausted.")
            return self.queue.pop(0)

        # Repair is checked first so a repair call is never misrouted.
        if self.REPAIR_TAG in system_prompt and self.repair is not None:
            return self.repair
        if self.RED_TAG in system_prompt and self.red is not None:
            return self.red
        if self.JUDGE_TAG in system_prompt and self.judge is not None:
            return self.judge
        if self.TUNING_TAG in system_prompt and self.tuning is not None:
            return self.tuning
        if self.default is not None:
            return self.default
        raise ProviderError(
            "FakeLLMProvider: no response configured for this call."
        )
