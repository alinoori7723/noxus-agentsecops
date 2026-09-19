import json

import m2_data
import pytest
from fastapi.testclient import TestClient

from noxus import api_core
from noxus.api_server import create_app
from noxus.llm_provider import FakeLLMProvider
from noxus.provider_profiles import is_loopback, load_profiles

PROFILE = {
    "provider_type": "gemini_native",
    "api_key_env": "NOXUS_TEST_PROVIDER_SECRET",
    "red_model": "test-red",
    "judge_model": "test-judge",
    "tuning_model": "test-tuning",
}
SECRET = "test-only-provider-credential-never-return"


@pytest.fixture()
def profiles(monkeypatch):
    monkeypatch.setenv("NOXUS_PROVIDER_PROFILES", json.dumps({"gemini-test": PROFILE}))
    monkeypatch.setenv("NOXUS_TEST_PROVIDER_SECRET", SECRET)
    monkeypatch.delenv("NOXUS_ENABLE_MANUAL_KEYS", raising=False)
    return TestClient(create_app(), client=("127.0.0.1", 50000))


@pytest.mark.parametrize("endpoint", ["/api/providers/test", "/api/assessments/run"])
def test_manual_credentials_are_disabled_by_default(profiles, endpoint):
    response = profiles.post(endpoint, json={"provider_config": {"api_key": SECRET}})
    assert response.status_code == 403
    assert SECRET not in response.text


@pytest.mark.parametrize("host", ["198.51.100.1", "10.0.0.5", "::ffff:192.0.2.1"])
def test_manual_opt_in_rejects_non_loopback_connections(profiles, monkeypatch, host):
    monkeypatch.setenv("NOXUS_ENABLE_MANUAL_KEYS", "true")
    client = TestClient(create_app(), client=(host, 50000))
    response = client.post(
        "/api/providers/test",
        json={"provider_config": {"api_key": SECRET}},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert response.status_code == 403
    assert client.get("/api/providers").json()["manual_keys_enabled"] is False


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("127.10.1.5", True),
        ("localhost", False),
        (None, False),
        ("invalid", False),
    ],
)
def test_loopback_detection_uses_peer_addresses(host, expected):
    assert is_loopback(host) is expected


def test_profile_catalog_never_exposes_credentials_or_endpoints(profiles):
    response = profiles.get("/api/providers")
    assert response.json() == {
        "profiles": [{"name": "gemini-test", "provider_type": "gemini_native"}],
        "manual_keys_enabled": False,
    }
    assert SECRET not in response.text
    assert "NOXUS_TEST_PROVIDER_SECRET" not in response.text


def test_profile_resolves_credentials_only_on_server(profiles, monkeypatch, caplog):
    configs = []
    fake = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.PATCHSET_WITH_RAIL,
    )

    def build(config):
        configs.append(config)
        return fake, {
            "red_model": config.red_model,
            "judge_model": config.judge_model,
            "tuning_model": config.tuning_model,
        }

    monkeypatch.setattr(api_core, "build_provider", build)
    response = profiles.post(
        "/api/providers/test", json={"provider_profile": "gemini-test", "models_to_test": ["red"]}
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert configs[0].api_key == SECRET
    assert configs[0].red_model == "test-red"
    assert SECRET not in response.text + caplog.text + repr(configs[0])


def test_profile_assessment_runs_without_browser_credentials(profiles, monkeypatch):
    seen = []

    def run(req):
        seen.append(req)
        return None, {"ok": True}

    monkeypatch.setattr(api_core, "run_assessment", run)
    response = profiles.post(
        "/api/assessments/run", json={"mode": "agent_assisted", "provider_profile": "gemini-test"}
    )
    assert response.json() == {"ok": True}
    assert seen[0].provider_config.api_key == SECRET


def test_profile_cannot_be_overridden_with_client_endpoint(profiles):
    response = profiles.post(
        "/api/providers/test",
        json={
            "provider_profile": "gemini-test",
            "provider_config": {"api_key": SECRET, "base_url": "http://169.254.169.254"},
        },
    )
    assert response.status_code == 400
    assert SECRET not in response.text


def test_unknown_profile_fails_without_provider_call(profiles, monkeypatch):
    def unexpected(*args):
        raise AssertionError("Provider must not be called")

    monkeypatch.setattr(api_core, "build_provider", unexpected)
    assert (
        profiles.post("/api/providers/test", json={"provider_profile": "unknown"}).status_code
        == 400
    )


@pytest.mark.parametrize("credential", [None, "", "   "])
def test_missing_server_secret_fails_closed(profiles, monkeypatch, credential):
    if credential is None:
        monkeypatch.delenv("NOXUS_TEST_PROVIDER_SECRET")
    else:
        monkeypatch.setenv("NOXUS_TEST_PROVIDER_SECRET", credential)
    response = profiles.post("/api/providers/test", json={"provider_profile": "gemini-test"})
    assert response.status_code == 503
    assert "NOXUS_TEST_PROVIDER_SECRET" not in response.text


@pytest.mark.parametrize(
    "raw", ["invalid-json", "[]", '{"bad.name":{}}', '{"x":{"api_key":"sensitive-value"}}']
)
def test_bad_server_config_returns_generic_error(profiles, monkeypatch, raw):
    monkeypatch.setenv("NOXUS_PROVIDER_PROFILES", raw)
    response = profiles.get("/api/providers")
    assert response.status_code == 503
    assert raw not in response.text
    assert "sensitive-value" not in response.text


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.com",
        "https://user:password@example.com",
        "https://example.com?key=secret",
        "file:///etc/passwd",
        "https://example.com/#key",
        "",
    ],
)
def test_profiles_reject_unsafe_endpoints(profiles, monkeypatch, endpoint):
    config = {**PROFILE, "provider_type": "openai_compatible", "base_url": endpoint}
    monkeypatch.setenv("NOXUS_PROVIDER_PROFILES", json.dumps({"test": config}))
    with pytest.raises(api_core.ApiError, match="not configured correctly"):
        load_profiles()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://gateway.example/v1",
        "http://127.0.0.1:4000/v1",
        "http://[::1]:4000/v1",
        "http://localhost:4000/v1",
    ],
)
def test_profiles_accept_secure_or_loopback_endpoints(profiles, monkeypatch, endpoint):
    config = {**PROFILE, "provider_type": "openai_compatible", "base_url": endpoint}
    monkeypatch.setenv("NOXUS_PROVIDER_PROFILES", json.dumps({"test": config}))
    assert load_profiles()["test"].base_url == endpoint


@pytest.mark.parametrize(
    "body",
    [
        {"provider_config": {"api_key": {"secret": SECRET}}},
        {"unexpected": SECRET},
        {"provider_profile": SECRET + "/invalid"},
    ],
)
def test_validation_errors_do_not_reflect_inputs(profiles, body):
    response = profiles.post("/api/providers/test", json=body)
    assert response.status_code == 422
    assert SECRET not in response.text


def test_manual_keys_work_only_when_opted_in_on_loopback(profiles, monkeypatch):
    monkeypatch.setenv("NOXUS_ENABLE_MANUAL_KEYS", "true")
    seen = []
    monkeypatch.setattr(
        api_core, "test_provider", lambda config, roles: seen.append(config.api_key) or {"ok": True}
    )
    assert profiles.get("/api/providers").json()["manual_keys_enabled"] is True
    response = profiles.post("/api/providers/test", json={"provider_config": {"api_key": SECRET}})
    assert response.json() == {"ok": True}
    assert seen == [SECRET]


@pytest.mark.parametrize("name", ["", "x" * 81, "profilé"])
def test_invalid_profile_names_are_configuration_failures(profiles, monkeypatch, name):
    monkeypatch.setenv("NOXUS_PROVIDER_PROFILES", json.dumps({name: PROFILE}))
    response = profiles.get("/api/providers")
    assert response.status_code == 503
    assert response.json()["detail"] == "Server provider profiles are not configured correctly."


def test_gemini_profile_cannot_override_its_fixed_endpoint(profiles, monkeypatch):
    config = {**PROFILE, "base_url": "https://unexpected.example"}
    monkeypatch.setenv("NOXUS_PROVIDER_PROFILES", json.dumps({"test": config}))
    assert profiles.get("/api/providers").status_code == 503


def test_local_profile_uses_the_loopback_default(profiles, monkeypatch):
    config = {**PROFILE, "provider_type": "local_openai_compatible"}
    monkeypatch.setenv("NOXUS_PROVIDER_PROFILES", json.dumps({"local": config}))
    response = profiles.get("/api/providers")
    assert response.status_code == 200
    assert response.json()["profiles"] == [
        {"name": "local", "provider_type": "local_openai_compatible"}
    ]
    assert load_profiles()["local"].base_url is None
