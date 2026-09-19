from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable

DEFAULT_TIMEOUT = 30.0


class ProviderError(Exception):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderNetworkError(ProviderError):
    pass


class ProviderAuthError(ProviderError):
    pass


@runtime_checkable
class LLMProvider(Protocol):
    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema_instruction: str | None = None,
        timeout: float | None = None,
    ) -> str: ...


class LiteLLMProvider:
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
        json_schema_instruction: str | None = None,
        timeout: float | None = None,
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
            if exc.code in (401, 403):
                raise ProviderAuthError(
                    f"Authentication failed at LLM endpoint: {exc.code}"
                ) from exc
            raise ProviderError(f"HTTP error from LLM endpoint: {exc.code}") from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), socket.timeout):
                raise ProviderTimeoutError("LLM request timed out.") from exc
            raise ProviderNetworkError("Network error contacting LLM endpoint.") from exc
        except TimeoutError as exc:
            raise ProviderTimeoutError("LLM request timed out.") from exc

        try:
            parsed = json.loads(body)
            content = parsed["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("Expected text content")
            return content.replace(self.api_key, "***REDACTED***")
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderError("Malformed response from LLM endpoint.") from exc


class GeminiNativeProvider:
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not api_key:
            raise ProviderError("GeminiNativeProvider requires a non-empty api_key.")
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    def _endpoint(self, model: str) -> str:

        name = model[len("models/") :] if model.startswith("models/") else model
        return f"{self.base_url}/v1beta/models/{name}:generateContent"

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema_instruction: str | None = None,
        timeout: float | None = None,
    ) -> str:
        system_content = system_prompt
        if json_schema_instruction:
            system_content = f"{system_prompt}\n\n{json_schema_instruction}"

        payload = {
            "system_instruction": {"parts": [{"text": system_content}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0},
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint(model),
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
        )
        effective_timeout = self.timeout if timeout is None else timeout
        try:
            with urllib.request.urlopen(request, timeout=effective_timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ProviderAuthError(
                    f"Authentication failed at Gemini endpoint: {exc.code}"
                ) from exc
            raise ProviderError(f"HTTP error from Gemini endpoint: {exc.code}") from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), socket.timeout):
                raise ProviderTimeoutError("Gemini request timed out.") from exc
            raise ProviderNetworkError("Network error contacting Gemini endpoint.") from exc
        except TimeoutError as exc:
            raise ProviderTimeoutError("Gemini request timed out.") from exc

        try:
            parsed = json.loads(body)
            parts = parsed["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts).replace(
                self.api_key, "***REDACTED***"
            )
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderError("Malformed response from Gemini endpoint.") from exc


class FakeLLMProvider:
    RED_TAG = "[NOXUS_RED_TEAM]"
    JUDGE_TAG = "[NOXUS_JUDGE]"
    TUNING_TAG = "[NOXUS_TUNING]"
    REPAIR_TAG = "[NOXUS_REPAIR]"

    def __init__(
        self,
        *,
        red: str | None = None,
        judge: str | None = None,
        tuning: str | None = None,
        repair: str | None = None,
        default: str | None = None,
        queue: list[str] | None = None,
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
        json_schema_instruction: str | None = None,
        timeout: float | None = None,
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
        raise ProviderError("FakeLLMProvider: no response configured for this call.")
