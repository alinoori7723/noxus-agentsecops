import io
import json
import urllib.error
import urllib.request

import pytest

from noxus.llm_provider import (
    GeminiNativeProvider,
    LiteLLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderNetworkError,
    ProviderTimeoutError,
)

KEY = "synthetic-provider-credential"


@pytest.fixture(params=["gemini", "litellm"])
def provider(request):
    if request.param == "gemini":
        return GeminiNativeProvider(KEY)
    return LiteLLMProvider("https://gateway.example/v1", KEY)


def test_transport_uses_headers_and_redacts_echoed_credential(provider, monkeypatch):
    calls = []

    def urlopen(request, timeout):
        calls.append((request, timeout))
        payload = (
            {"candidates": [{"content": {"parts": [{"text": KEY}]}}]}
            if isinstance(provider, GeminiNativeProvider)
            else {"choices": [{"message": {"content": KEY}}]}
        )
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    result = provider.complete(
        model="models/test-model",
        system_prompt="system",
        user_prompt="user",
        json_schema_instruction="schema",
        timeout=7,
    )
    assert result == "***REDACTED***"
    request, timeout = calls[0]
    assert timeout == 7
    assert KEY not in request.full_url
    assert KEY.encode() not in request.data
    assert any(KEY in value for value in request.headers.values())
    if isinstance(provider, GeminiNativeProvider):
        assert request.full_url.endswith("/models/test-model:generateContent")
    else:
        assert request.full_url.endswith("/v1/chat/completions")


@pytest.mark.parametrize(
    "status,error_type",
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderError),
        (500, ProviderError),
    ],
)
def test_http_failure_never_echoes_server_reason_or_body(provider, monkeypatch, status, error_type):
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://provider.example", status, KEY, {}, io.BytesIO(KEY.encode())
        )

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(error_type) as raised:
        provider.complete(model="test", system_prompt="s", user_prompt="u")
    assert KEY not in str(raised.value)
    assert str(status) in str(raised.value)


@pytest.mark.parametrize(
    "error,error_type",
    [
        (TimeoutError(), ProviderTimeoutError),
        (urllib.error.URLError(TimeoutError()), ProviderTimeoutError),
        (urllib.error.URLError(KEY), ProviderNetworkError),
    ],
)
def test_transient_failures_are_classified_without_leaking_details(
    provider, monkeypatch, error, error_type
):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(error_type) as raised:
        provider.complete(model="test", system_prompt="s", user_prompt="u")
    assert KEY not in str(raised.value)


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"{}",
        b'{"choices":[],"candidates":[]}',
        b'{"choices":[{"message":{"content":null}}],"candidates":[{"content":{"parts":[null]}}]}',
    ],
)
def test_malformed_provider_responses_fail_closed(provider, monkeypatch, body):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(body))
    with pytest.raises(ProviderError, match="Malformed response"):
        provider.complete(model="test", system_prompt="s", user_prompt="u")
