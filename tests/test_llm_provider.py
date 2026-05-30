from noxus.llm_provider import FakeLLMProvider, ProviderError

import pytest


def test_fake_llm_provider_returns_configured_response():
    fake = FakeLLMProvider(red="RED_RESPONSE")
    out = fake.complete(
        model="m",
        system_prompt="[NOXUS_RED_TEAM] generate probes",
        user_prompt="please",
    )
    assert out == "RED_RESPONSE"
    assert len(fake.calls) == 1
    assert fake.calls[0]["model"] == "m"


def test_fake_llm_provider_raises_when_unconfigured():
    fake = FakeLLMProvider()
    with pytest.raises(ProviderError):
        fake.complete(model="m", system_prompt="no tag", user_prompt="x")
