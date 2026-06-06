"""HTTP-level tests for the FastAPI server.

These require fastapi + a test transport (httpx). They are skipped automatically
when those test-only packages are not installed in the host environment, so the
base ``pytest`` run stays green without the web stack. The framework-free logic
is fully covered in ``test_api_core``.
"""

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from noxus.api_server import app, create_app  # noqa: E402

_SENTINEL_KEY = "sk-HTTP-SENTINEL-DO-NOT-LEAK-9z9z"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "product": "Noxus AgentSecOps", "mode": "api"}


def test_sample_inputs_endpoint(client):
    r = client.get("/api/sample-inputs")
    assert r.status_code == 200
    assert set(r.json().keys()) == {
        "system_prompt",
        "security_policy_yaml",
        "business_context",
    }


def test_deterministic_assessment_endpoint(client):
    s = client.get("/api/sample-inputs").json()
    r = client.post(
        "/api/assessments/run",
        json={
            "mode": "deterministic",
            "system_prompt": s["system_prompt"],
            "security_policy_yaml": s["security_policy_yaml"],
            "business_context": s["business_context"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["readiness"]["badge"]["state"] == "CONDITIONAL_PASS"
    assert body["evidence"]["proprietary_context_exposure_unresolved"] is True
    assert _SENTINEL_KEY not in r.text


def test_agent_assisted_missing_config_returns_400(client):
    r = client.post("/api/assessments/run", json={"mode": "agent_assisted"})
    assert r.status_code == 400
    assert "provider_config" in r.json()["detail"]


def test_provider_failure_does_not_echo_api_key(client, monkeypatch):
    # An unreachable endpoint is a transient network failure. With the
    # deterministic baseline preserved this now returns a partial
    # HUMAN_REVIEW_REQUIRED report (Fix 5); otherwise a clean 4xx/5xx. In every
    # case the api_key must NEVER appear in the response text.
    monkeypatch.setenv("NOXUS_LLM_MAX_RETRIES", "0")  # keep the test fast
    monkeypatch.setenv("NOXUS_LLM_RETRY_BACKOFF_SECONDS", "0")
    s = client.get("/api/sample-inputs").json()
    r = client.post(
        "/api/assessments/run",
        json={
            "mode": "agent_assisted",
            "system_prompt": s["system_prompt"],
            "security_policy_yaml": s["security_policy_yaml"],
            "business_context": s["business_context"],
            "provider_config": {
                "provider_type": "openai_compatible",
                "base_url": "http://127.0.0.1:9/v1",
                "api_key": _SENTINEL_KEY,
                "red_model": "m",
                "judge_model": "m",
                "tuning_model": "m",
            },
        },
    )
    assert r.status_code in (200, 400, 502, 504)
    assert _SENTINEL_KEY not in r.text
    if r.status_code == 200:
        # Partial report path: baseline preserved, role-tagged, no key leak.
        assert r.json()["readiness_state"] == "HUMAN_REVIEW_REQUIRED"


def _det_report(client):
    s = client.get("/api/sample-inputs").json()
    return client.post(
        "/api/assessments/run",
        json={
            "mode": "deterministic",
            "system_prompt": s["system_prompt"],
            "security_policy_yaml": s["security_policy_yaml"],
            "business_context": s["business_context"],
        },
    ).json()


def test_audit_export_endpoint_writes_only_under_configured_audit_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NOXUS_AUDIT_DIR", str(tmp_path))
    from noxus.api_server import create_app

    c = TestClient(create_app())
    run = _det_report(c)
    r = c.post(
        "/api/audit/export-local",
        json={"report": run["report"], "filename": "audit.jsonl"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    written = Path(r.json()["path"]).resolve()
    assert str(written).startswith(str(tmp_path.resolve()))
    record = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip())
    assert record["readiness_state"] == "CONDITIONAL_PASS"


def test_audit_export_endpoint_rejects_absolute_path(client, tmp_path):
    run = _det_report(client)
    r = client.post(
        "/api/audit/export-local",
        json={"report": run["report"], "filename": "/etc/evil.jsonl"},
    )
    assert r.status_code == 400


def test_audit_export_endpoint_rejects_parent_traversal_filename(client):
    run = _det_report(client)
    r = client.post(
        "/api/audit/export-local",
        json={"report": run["report"], "filename": "../../escape.jsonl"},
    )
    assert r.status_code == 400


def test_audit_export_endpoint_does_not_accept_arbitrary_server_path(client, tmp_path):
    run = _det_report(client)
    target = tmp_path / "arbitrary.jsonl"
    # extra="forbid" -> the removed output_path field is rejected (422), and the
    # arbitrary location is never written.
    r = client.post(
        "/api/audit/export-local",
        json={"report": run["report"], "output_path": str(target)},
    )
    assert r.status_code == 422
    assert not target.exists()


def test_audit_export_endpoint_does_not_echo_api_key_or_provider_config(client):
    run = _det_report(client)
    r = client.post(
        "/api/audit/export-local",
        json={"report": run["report"], "filename": "noecho.jsonl"},
    )
    # Deterministic report carries no provider config / key in the first place.
    assert "api_key" not in r.text
    assert "provider_config" not in r.text


# --------------------------------------------------------------------------- #
# SPA static serving — path-traversal confinement
# --------------------------------------------------------------------------- #
@pytest.fixture()
def spa_client(tmp_path, monkeypatch):
    """A TestClient over a controlled static dir, with a secret file OUTSIDE it."""
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("INDEX_SPA_MARKER", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (static / "favicon.ico").write_text("icon", encoding="utf-8")
    # Secret sibling outside the static root that must never be served.
    (tmp_path / "secret.txt").write_text("TOPSECRET_OUTSIDE_ROOT", encoding="utf-8")
    monkeypatch.setenv("NOXUS_WEB_DIST", str(static))
    return TestClient(create_app())


def test_spa_fallback_serves_index_for_allowlisted_route(spa_client):
    # An allowlisted client route receives the SPA shell...
    r = spa_client.get("/assessment")
    assert r.status_code == 200
    assert "INDEX_SPA_MARKER" in r.text


def test_spa_fallback_rejects_unknown_nested_route(spa_client):
    # ...but a non-allowlisted (and file-looking) deep path must 404, not index.
    r = spa_client.get("/dashboard/settings")
    assert r.status_code == 404


def test_static_file_serving_is_confined_to_static_root(spa_client, tmp_path):
    # A real file inside the root is served...
    ok = spa_client.get("/assets/app.js")
    assert ok.status_code == 200
    # ...but a sibling outside the root is never reachable via traversal.
    for attempt in (
        "/..%2fsecret.txt",
        "/..%2f..%2fsecret.txt",
        "/%2e%2e/secret.txt",
    ):
        r = spa_client.get(attempt)
        assert "TOPSECRET_OUTSIDE_ROOT" not in r.text
        assert r.status_code in (404, 200)  # 200 only if it fell back to index
        if r.status_code == 200:
            assert "INDEX_SPA_MARKER" in r.text


def test_spa_fallback_rejects_parent_traversal(spa_client):
    r = spa_client.get("/..%2f..%2f..%2fsecret.txt")
    assert "TOPSECRET_OUTSIDE_ROOT" not in r.text


def test_spa_fallback_does_not_serve_pyproject(client):
    # The repo's real app (static root = apps/web/dist). Traversal toward the
    # backend's pyproject must not leak it.
    for attempt in (
        "/..%2f..%2f..%2fpyproject.toml",
        "/..%2f..%2f..%2f..%2fpyproject.toml",
        "/%2e%2e/%2e%2e/%2e%2e/pyproject.toml",
    ):
        r = client.get(attempt)
        assert "[project]" not in r.text
        assert "dependencies" not in r.text or "INDEX" in r.text.upper()


def test_spa_fallback_does_not_serve_backend_source(client):
    for attempt in (
        "/..%2f..%2f..%2fsrc%2fnoxus%2fapi_core.py",
        "/..%2f..%2f..%2f..%2fsrc%2fnoxus%2fapi_server.py",
    ):
        r = client.get(attempt)
        assert "def run_assessment" not in r.text
        assert "FastAPI" not in r.text


# --------------------------------------------------------------------------- #
# CORS — never wildcard by default; dev CORS is env-gated
# --------------------------------------------------------------------------- #
def test_cors_not_wildcard_by_default(monkeypatch):
    monkeypatch.delenv("NOXUS_ENABLE_DEV_CORS", raising=False)
    c = TestClient(create_app())
    r = c.get("/api/health", headers={"Origin": "http://evil.example"})
    assert r.headers.get("access-control-allow-origin") != "*"
    # No CORS middleware at all by default -> header simply absent.
    assert "access-control-allow-origin" not in r.headers


def test_dev_cors_requires_env_flag(monkeypatch):
    # Without the flag: no CORS reflected.
    monkeypatch.delenv("NOXUS_ENABLE_DEV_CORS", raising=False)
    c_off = TestClient(create_app())
    off = c_off.get(
        "/api/health", headers={"Origin": "http://localhost:5173"}
    )
    assert "access-control-allow-origin" not in off.headers

    # With the flag: CORS reflected for the allowed origin, never wildcard.
    monkeypatch.setenv("NOXUS_ENABLE_DEV_CORS", "true")
    monkeypatch.setenv(
        "NOXUS_DEV_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    c_on = TestClient(create_app())
    on = c_on.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert on.headers.get("access-control-allow-origin") == "http://localhost:5173"
    # A non-allowed origin is not reflected.
    other = c_on.get("/api/health", headers={"Origin": "http://evil.example"})
    assert other.headers.get("access-control-allow-origin") not in ("*", "http://evil.example")


# --------------------------------------------------------------------------- #
# Provider connectivity test endpoint + agent trace
# --------------------------------------------------------------------------- #
def test_provider_test_endpoint_missing_key_returns_400(client):
    r = client.post(
        "/api/providers/test",
        json={
            "provider_config": {"provider_type": "gemini_native"},
            "models_to_test": ["red"],
        },
    )
    assert r.status_code == 400


def test_provider_test_endpoint_unreachable_does_not_echo_key(client):
    r = client.post(
        "/api/providers/test",
        json={
            "provider_config": {
                "provider_type": "openai_compatible",
                "base_url": "http://127.0.0.1:9/v1",
                "api_key": _SENTINEL_KEY,
                "red_model": "m1",
                "judge_model": "m2",
                "tuning_model": "m3",
            },
            "models_to_test": ["red", "judge", "tuning"],
        },
    )
    assert r.status_code == 200  # the endpoint reports per-model failures cleanly
    body = r.json()
    assert body["ok"] is False
    assert _SENTINEL_KEY not in r.text
    assert {res["role"] for res in body["results"]} == {"red", "judge", "tuning"}


def test_provider_test_endpoint_writes_no_audit_files(tmp_path, monkeypatch):
    monkeypatch.setenv("NOXUS_AUDIT_DIR", str(tmp_path))
    from noxus.api_server import create_app

    c = TestClient(create_app())
    c.post(
        "/api/providers/test",
        json={
            "provider_config": {
                "provider_type": "openai_compatible",
                "base_url": "http://127.0.0.1:9/v1",
                "api_key": "k",
                "red_model": "m",
            },
            "models_to_test": ["red"],
        },
    )
    assert list(tmp_path.iterdir()) == []


def test_run_response_includes_agent_trace(client):
    s = client.get("/api/sample-inputs").json()
    r = client.post(
        "/api/assessments/run",
        json={
            "mode": "deterministic",
            "system_prompt": s["system_prompt"],
            "security_policy_yaml": s["security_policy_yaml"],
            "business_context": s["business_context"],
        },
    )
    body = r.json()
    assert body["execution_mode"] == "deterministic"
    trace = body["agent_trace"]
    stages = {st["stage"] for st in trace["stages"]}
    assert {"red_team", "semantic_judge", "policy_tuning", "patch_application"} <= stages


# --------------------------------------------------------------------------- #
# Clean validation errors (base URL + policy schema)
# --------------------------------------------------------------------------- #
def test_run_endpoint_invalid_base_url_returns_clean_400(client):
    s = client.get("/api/sample-inputs").json()
    r = client.post(
        "/api/assessments/run",
        json={
            "mode": "agent_assisted",
            "system_prompt": s["system_prompt"],
            "security_policy_yaml": s["security_policy_yaml"],
            "business_context": s["business_context"],
            "provider_config": {
                "provider_type": "openai_compatible",
                "base_url": "localhost:4000/v1",
                "api_key": "k",
                "red_model": "m",
                "judge_model": "m",
                "tuning_model": "m",
            },
        },
    )
    assert r.status_code == 400
    assert "http://" in r.text
    assert "unknown url type" not in r.text.lower()


def test_run_endpoint_unsupported_policy_returns_structured_400(client):
    s = client.get("/api/sample-inputs").json()
    r = client.post(
        "/api/assessments/run",
        json={
            "mode": "deterministic",
            "system_prompt": s["system_prompt"],
            "security_policy_yaml": "bogus_top: true\n",
            "business_context": s["business_context"],
        },
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "policy_schema"
    assert "bogus_top" in detail["unsupported_keys"]
    assert detail["allowed_keys"]
    # No raw Pydantic dump leaks to the client.
    assert "pydantic" not in r.text.lower()
    assert "Extra inputs are not permitted" not in r.text


def test_provider_test_endpoint_invalid_base_url_returns_400(client):
    r = client.post(
        "/api/providers/test",
        json={
            "provider_config": {
                "provider_type": "openai_compatible",
                "base_url": "localhost:4000/v1",
                "api_key": "k",
                "red_model": "m",
            },
            "models_to_test": ["red"],
        },
    )
    assert r.status_code == 400
    assert "http://" in r.text


# --------------------------------------------------------------------------- #
# Provider test endpoint — REAL role-schema contract validation
# --------------------------------------------------------------------------- #
import m2_data  # noqa: E402
from noxus import api_core as _api_core  # noqa: E402
from noxus.llm_provider import FakeLLMProvider  # noqa: E402


def test_provider_test_endpoint_validates_real_role_schemas(client, monkeypatch):
    fake = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_VIOLATION,
        tuning=m2_data.EMPTY_PATCHSET,
    )
    monkeypatch.setattr(
        _api_core, "build_provider",
        lambda cfg: (fake, {"red_model": "r", "judge_model": "j", "tuning_model": "t"}),
    )
    r = client.post(
        "/api/providers/test",
        json={
            "provider_config": {"provider_type": "gemini_native", "api_key": _SENTINEL_KEY},
            "models_to_test": ["red", "judge", "tuning"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert all(res["ok"] and "schema contract" in res["message"] for res in body["results"])
    assert _SENTINEL_KEY not in r.text


def test_provider_test_endpoint_generic_json_fails_role_contract(client, monkeypatch):
    fake = FakeLLMProvider(default='{"noxus_provider_check": true}')
    monkeypatch.setattr(
        _api_core, "build_provider",
        lambda cfg: (fake, {"red_model": "r", "judge_model": "j", "tuning_model": "t"}),
    )
    r = client.post(
        "/api/providers/test",
        json={
            "provider_config": {"provider_type": "gemini_native", "api_key": _SENTINEL_KEY},
            "models_to_test": ["red"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    res = body["results"][0]
    assert res["response_validated"] is False
    assert "did not satisfy the red schema contract" in res["message"]
    assert res["debug_excerpt"]
    assert _SENTINEL_KEY not in r.text


# --------------------------------------------------------------------------- #
# SPA fallback (Codex blocker #3): only allowlisted client routes get the SPA
# shell; filesystem-looking paths must 404, never the index. (Reuses the
# module-level ``spa_client`` fixture defined above.)
# --------------------------------------------------------------------------- #
def test_spa_fallback_allows_root(spa_client):
    r = spa_client.get("/")
    assert r.status_code == 200
    assert "INDEX_SPA_MARKER" in r.text


@pytest.mark.parametrize(
    "route",
    ["/overview", "/assessment", "/results", "/evidence", "/open-risks",
     "/provider-settings", "/engineering-proof", "/target-config"],
)
def test_spa_fallback_allows_known_frontend_routes(spa_client, route):
    r = spa_client.get(route)
    assert r.status_code == 200
    assert "INDEX_SPA_MARKER" in r.text


def test_spa_fallback_serves_real_static_asset(spa_client):
    assert spa_client.get("/favicon.ico").status_code == 200
    assert spa_client.get("/assets/app.js").status_code == 200


def test_spa_fallback_rejects_etc_passwd(spa_client):
    assert spa_client.get("/etc/passwd").status_code == 404


def test_spa_fallback_rejects_app_pyproject(spa_client):
    assert spa_client.get("/app/pyproject.toml").status_code == 404


def test_spa_fallback_rejects_src_backend_path(spa_client):
    assert spa_client.get("/src/noxus/api_core.py").status_code == 404


def test_spa_fallback_rejects_unknown_file_like_path(spa_client):
    assert spa_client.get("/package.json").status_code == 404
    assert spa_client.get("/dashboard").status_code == 404


def test_spa_fallback_rejects_encoded_traversal(spa_client):
    # %2e%2e/ decodes to ../ ; must not escape or be treated as a client route.
    r = spa_client.get("/%2e%2e/pyproject.toml")
    assert r.status_code == 404
    r2 = spa_client.get("/../pyproject.toml")
    assert r2.status_code == 404
