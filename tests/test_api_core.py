"""Tests for the framework-free API core (no FastAPI needed to run these).

Covers the deterministic assessment contract, agent-assisted config validation,
provider construction, API-key redaction/non-echo, and audit export.
"""

import json
from pathlib import Path

import pytest

import m2_data
from noxus import api_core
from noxus.llm_provider import FakeLLMProvider, GeminiNativeProvider, LiteLLMProvider
from noxus.orchestrator import run_readiness_assessment

_SENTINEL_KEY = "sk-SENTINEL-DO-NOT-LEAK-abc123XYZ"


def _det_request() -> api_core.RunAssessmentRequest:
    s = api_core.sample_inputs()
    return api_core.RunAssessmentRequest(
        mode="deterministic",
        system_prompt=s["system_prompt"],
        security_policy_yaml=s["security_policy_yaml"],
        business_context=s["business_context"],
    )


def test_health_payload_shape():
    assert api_core.health_payload() == {
        "ok": True,
        "product": "Noxus AgentSecOps",
        "mode": "api",
    }


def test_sample_inputs_has_all_three_inputs():
    s = api_core.sample_inputs()
    assert set(s.keys()) == {
        "system_prompt",
        "security_policy_yaml",
        "business_context",
    }
    assert s["system_prompt"].strip()
    assert s["security_policy_yaml"].strip()


def test_deterministic_run_is_conditional_pass_with_open_risk():
    _report, resp = api_core.run_assessment(_det_request())
    badge = resp["readiness"]["badge"]
    assert badge["state"] == "CONDITIONAL_PASS"
    assert badge["color"] == "amber"
    assert badge["is_pass"] is False
    # Open risk + proprietary-context exposure remain visible.
    assert resp["evidence"]["open_risks"]
    assert resp["evidence"]["proprietary_context_exposure_unresolved"] is True
    assert any(
        "proprietary_context_exposure" in r for r in resp["evidence"]["open_risks"]
    )
    # Real safety-rail telemetry, not a placeholder.
    preview = resp["red_blue"]["blue"]["safety_rail_preview"]
    assert "[CRITICAL_SAFETY_RAILS]" in preview
    assert "<critical safety rail clause>" not in preview


def test_deterministic_run_requires_no_provider_and_holds_no_key():
    _report, resp = api_core.run_assessment(_det_request())
    blob = json.dumps(resp)
    # The deterministic path never involves any provider api_key value.
    assert _SENTINEL_KEY not in blob


def test_detection_labels_present_in_response():
    _report, resp = api_core.run_assessment(_det_request())
    labels = {
        p["detection_label"]
        for p in resp["red_blue"]["red"]["baseline_probes"]
    }
    assert "[DETERMINISTIC SIMULATION]" in labels


def test_agent_assisted_missing_config_is_clean_400():
    req = api_core.RunAssessmentRequest(mode="agent_assisted", provider_config=None)
    with pytest.raises(api_core.ApiError) as exc:
        api_core.run_assessment(req)
    assert exc.value.status_code == 400
    assert "provider_config" in exc.value.message


def test_agent_assisted_missing_api_key_is_400():
    cfg = api_core.ProviderConfig(provider_type="openai_compatible", base_url="http://x/v1")
    with pytest.raises(api_core.ApiError) as exc:
        api_core.build_provider(cfg)
    assert exc.value.status_code == 400
    assert "api_key" in exc.value.message


def test_unknown_provider_type_is_400():
    cfg = api_core.ProviderConfig(provider_type="not_a_provider", api_key="k")
    with pytest.raises(api_core.ApiError) as exc:
        api_core.build_provider(cfg)
    assert exc.value.status_code == 400


def test_build_provider_local_and_gemini():
    local, models = api_core.build_provider(
        api_core.ProviderConfig(
            provider_type="local_openai_compatible", api_key=_SENTINEL_KEY
        )
    )
    assert isinstance(local, LiteLLMProvider)
    # default local base url applied
    assert local.base_url == api_core.DEFAULT_LOCAL_BASE_URL
    assert models["red_model"] and models["judge_model"] and models["tuning_model"]

    gem, _ = api_core.build_provider(
        api_core.ProviderConfig(provider_type="gemini_native", api_key=_SENTINEL_KEY)
    )
    assert isinstance(gem, GeminiNativeProvider)


def test_redaction_never_exposes_api_key():
    cfg = api_core.ProviderConfig(
        provider_type="gemini_native", api_key=_SENTINEL_KEY, red_model="m"
    )
    red = api_core.redact_provider_config(cfg)
    assert red["api_key"] == "***REDACTED***"
    assert _SENTINEL_KEY not in json.dumps(red)

    req = api_core.RunAssessmentRequest(mode="agent_assisted", provider_config=cfg)
    log_view = api_core.redact_request(req)
    assert _SENTINEL_KEY not in json.dumps(log_view)
    assert log_view["provider_config"]["api_key"] == "***REDACTED***"


def test_invalid_policy_yaml_is_400():
    req = api_core.RunAssessmentRequest(
        mode="deterministic", security_policy_yaml="not: : a: mapping: ["
    )
    with pytest.raises(api_core.ApiError) as exc:
        api_core.run_assessment(req)
    assert exc.value.status_code == 400


def test_audit_export_writes_jsonl_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("NOXUS_AUDIT_DIR", str(tmp_path))
    _report, resp = api_core.run_assessment(_det_request())
    path = api_core.export_audit_local(resp["report"], "audit.jsonl")
    out = tmp_path / "audit.jsonl"
    assert out.exists()
    line = out.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["readiness_state"] == "CONDITIONAL_PASS"
    assert _SENTINEL_KEY not in line
    assert Path(path) == out


def test_audit_export_defaults_filename_under_audit_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NOXUS_AUDIT_DIR", str(tmp_path))
    _report, resp = api_core.run_assessment(_det_request())
    path = api_core.export_audit_local(resp["report"], None)
    assert Path(path) == (tmp_path / api_core.DEFAULT_AUDIT_FILENAME)
    assert (tmp_path / api_core.DEFAULT_AUDIT_FILENAME).exists()


@pytest.mark.parametrize(
    "bad",
    [
        "/etc/passwd",
        "../escape.jsonl",
        "../../secret.jsonl",
        "sub/dir.jsonl",
        "back\\slash.jsonl",
        "no_suffix",
        "..",
    ],
)
def test_audit_export_rejects_unsafe_filenames(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("NOXUS_AUDIT_DIR", str(tmp_path))
    _report, resp = api_core.run_assessment(_det_request())
    with pytest.raises(api_core.ApiError) as exc:
        api_core.export_audit_local(resp["report"], bad)
    assert exc.value.status_code == 400
    # Nothing escaped the audit dir.
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_audit_export_writes_only_under_configured_audit_dir(tmp_path, monkeypatch):
    audit = tmp_path / "audit_root"
    monkeypatch.setenv("NOXUS_AUDIT_DIR", str(audit))
    _report, resp = api_core.run_assessment(_det_request())
    path = Path(api_core.export_audit_local(resp["report"], "ok.jsonl")).resolve()
    assert str(path).startswith(str(audit.resolve()))


# --------------------------------------------------------------------------- #
# Static path-safety helper (used by the SPA fallback)
# --------------------------------------------------------------------------- #
def test_resolve_safe_static_path_allows_in_root(tmp_path):
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    safe = api_core.resolve_safe_static_path(tmp_path, "index.html")
    assert safe is not None and safe == (tmp_path / "index.html").resolve()


@pytest.mark.parametrize(
    "bad",
    ["../pyproject.toml", "../../etc/passwd", "/etc/passwd", "a/../../b", "/abs/x"],
)
def test_resolve_safe_static_path_rejects_traversal(tmp_path, bad):
    assert api_core.resolve_safe_static_path(tmp_path, bad) is None


def test_resolve_safe_static_path_allows_nonexistent_spa_route(tmp_path):
    # A client-side route (no such file) is still "safe" — caller serves index.
    safe = api_core.resolve_safe_static_path(tmp_path, "dashboard/settings")
    assert safe is not None


@pytest.mark.parametrize(
    "route", ["", "/", "overview", "/assessment", "open-risks", "engineering-proof"]
)
def test_is_frontend_route_allows_known_routes(route):
    assert api_core.is_frontend_route(route) is True


@pytest.mark.parametrize(
    "path",
    ["etc/passwd", "pyproject.toml", "package.json", "src/noxus/api_core.py",
     "../pyproject.toml", "app/pyproject.toml", "favicon.ico", "dashboard"],
)
def test_is_frontend_route_rejects_file_like_and_unknown(path):
    # File-looking / traversal / unknown paths are NOT client routes.
    assert api_core.is_frontend_route(path) is False


def test_agent_assisted_run_does_not_echo_key_on_provider_failure(monkeypatch):
    # Unreachable endpoint -> transient network error. With the deterministic
    # baseline preserved this now returns a partial HUMAN_REVIEW_REQUIRED report
    # (Fix 5) instead of a hard failure; the api_key must NEVER surface anywhere.
    monkeypatch.setenv("NOXUS_LLM_MAX_RETRIES", "0")  # keep the test fast
    monkeypatch.setenv("NOXUS_LLM_RETRY_BACKOFF_SECONDS", "0")
    cfg = api_core.ProviderConfig(
        provider_type="openai_compatible",
        base_url="http://127.0.0.1:9/v1",
        api_key=_SENTINEL_KEY,
        red_model="m",
        judge_model="m",
        tuning_model="m",
    )
    s = api_core.sample_inputs()
    req = api_core.RunAssessmentRequest(
        mode="agent_assisted",
        system_prompt=s["system_prompt"],
        security_policy_yaml=s["security_policy_yaml"],
        business_context=s["business_context"],
        provider_config=cfg,
    )
    try:
        _report, resp = api_core.run_assessment(req)
    except api_core.ApiError as exc:
        # If it DOES raise (e.g. no baseline evidence), the key still must not leak.
        assert _SENTINEL_KEY not in exc.message
        assert _SENTINEL_KEY not in json.dumps(exc.details)
        return
    # Partial report path: baseline preserved, role-tagged timeout, no key leak.
    assert resp["readiness_state"] == "HUMAN_REVIEW_REQUIRED"
    assert _SENTINEL_KEY not in json.dumps(resp)


def test_agent_assisted_with_fake_provider_preserves_semantics():
    """A schema-bound fake provider runs the agent loop end-to-end (no network)."""
    from noxus.llm_provider import FakeLLMProvider
    from noxus.orchestrator import run_readiness_assessment

    provider = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_VIOLATION,
        tuning=m2_data.EMPTY_PATCHSET,
    )
    report = run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
    )
    resp = api_core.build_assessment_response(report)
    # Semantic judgments surface honest labels through the API response.
    labels = {f["detection_label"] for f in resp["evidence"]["findings"]}
    assert "[SEMANTIC LLM JUDGMENT]" in labels


# --------------------------------------------------------------------------- #
# Agent trace (LLM role observability) — presentation only
# --------------------------------------------------------------------------- #
def test_deterministic_trace_marks_llm_roles_not_used():
    _report, resp = api_core.run_assessment(_det_request())
    trace = resp["agent_trace"]
    assert trace["execution_mode"] == "deterministic"
    assert trace["provider_type"] is None
    by_stage = {s["stage"]: s for s in trace["stages"]}
    assert by_stage["red_team"]["source"] == "deterministic_baseline"
    assert by_stage["semantic_judge"]["status"] == "not_used"
    assert by_stage["semantic_judge"]["source"] == "deterministic"
    assert by_stage["policy_tuning"]["source"] == "deterministic_mapper"
    assert by_stage["patch_application"]["source"] == "deterministic_engine"
    assert resp["execution_mode"] == "deterministic"


def test_agent_trace_marks_llm_sources_and_models():
    provider = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_VIOLATION,
        tuning=m2_data.EMPTY_PATCHSET,
    )
    report = run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
    )
    cfg = api_core.ProviderConfig(
        provider_type="gemini_native",
        api_key=_SENTINEL_KEY,
        red_model="rm",
        judge_model="jm",
        tuning_model="tm",
    )
    resp = api_core.build_assessment_response(
        report, mode="agent_assisted", provider_config=cfg
    )
    trace = resp["agent_trace"]
    assert trace["execution_mode"] == "agent_assisted"
    assert trace["provider_type"] == "gemini_native"
    assert trace["red_model"] == "rm" and trace["judge_model"] == "jm"
    by_stage = {s["stage"]: s for s in trace["stages"]}
    assert by_stage["red_team"]["source"] == "llm"
    assert by_stage["semantic_judge"]["source"] == "llm"
    assert trace["semantic_judgment_source"] == "llm"
    assert _SENTINEL_KEY not in json.dumps(resp)


# --------------------------------------------------------------------------- #
# Provider connectivity test
# --------------------------------------------------------------------------- #
def test_provider_test_requires_api_key():
    cfg = api_core.ProviderConfig(provider_type="openai_compatible", base_url="http://x/v1")
    with pytest.raises(api_core.ApiError) as exc:
        api_core.test_provider(cfg, ["red"])
    assert exc.value.status_code == 400
    assert "api_key" in exc.value.message


def test_provider_test_rejects_unknown_role():
    cfg = api_core.ProviderConfig(provider_type="gemini_native", api_key="k")
    with pytest.raises(api_core.ApiError) as exc:
        api_core.test_provider(cfg, ["bogus"])
    assert exc.value.status_code == 400


def test_provider_test_unreachable_is_sanitized_and_keyless():
    cfg = api_core.ProviderConfig(
        provider_type="openai_compatible",
        base_url="http://127.0.0.1:9/v1",
        api_key=_SENTINEL_KEY,
        red_model="m1",
        judge_model="m2",
        tuning_model="m3",
    )
    res = api_core.test_provider(cfg, ["red", "judge", "tuning"])
    assert res["ok"] is False
    assert _SENTINEL_KEY not in json.dumps(res)
    assert {r["role"] for r in res["results"]} == {"red", "judge", "tuning"}
    for r in res["results"]:
        assert r["ok"] is False
        assert r["response_validated"] is False
        assert _SENTINEL_KEY not in r["message"]
        assert isinstance(r["latency_ms"], int)


def test_provider_test_success_validates_real_role_contracts(monkeypatch):
    # Each role returns output valid for its REAL agent schema (tag-routed).
    fake = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_VIOLATION,
        tuning=m2_data.EMPTY_PATCHSET,
    )
    monkeypatch.setattr(
        api_core,
        "build_provider",
        lambda cfg: (fake, {"red_model": "r", "judge_model": "j", "tuning_model": "t"}),
    )
    cfg = api_core.ProviderConfig(provider_type="gemini_native", api_key=_SENTINEL_KEY)
    res = api_core.test_provider(cfg, ["red", "judge", "tuning"])
    assert res["ok"] is True
    assert res["provider_type"] == "gemini_native"
    assert all(r["ok"] and r["response_validated"] for r in res["results"])
    assert res["results"][0]["purpose"] == "Generates adversarial probes"
    assert all("schema contract" in r["message"] for r in res["results"])
    assert _SENTINEL_KEY not in json.dumps(res)
    assert "checked_at_utc" in res


def test_provider_test_generic_json_fails_role_contract(monkeypatch):
    # Valid generic JSON that does NOT satisfy the role schema -> failure, not
    # a false "connection successful".
    fake = FakeLLMProvider(default='{"noxus_provider_check": true}')
    monkeypatch.setattr(
        api_core,
        "build_provider",
        lambda cfg: (fake, {"red_model": "r", "judge_model": "j", "tuning_model": "t"}),
    )
    res = api_core.test_provider(
        api_core.ProviderConfig(provider_type="gemini_native", api_key=_SENTINEL_KEY),
        ["red", "judge", "tuning"],
    )
    assert res["ok"] is False
    for r in res["results"]:
        assert r["ok"] is False and r["response_validated"] is False
        assert "did not satisfy the" in r["message"]
        assert r["debug_excerpt"]  # sanitized snippet present
    assert _SENTINEL_KEY not in json.dumps(res)


@pytest.mark.parametrize("role", ["red", "judge", "tuning"])
def test_provider_test_validates_each_role_schema(monkeypatch, role):
    fake = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_VIOLATION,
        tuning=m2_data.EMPTY_PATCHSET,
    )
    monkeypatch.setattr(
        api_core,
        "build_provider",
        lambda cfg: (fake, {"red_model": "r", "judge_model": "j", "tuning_model": "t"}),
    )
    res = api_core.test_provider(
        api_core.ProviderConfig(provider_type="gemini_native", api_key="k"), [role]
    )
    assert len(res["results"]) == 1 and res["results"][0]["role"] == role
    assert res["results"][0]["ok"] is True


def test_provider_test_writes_no_audit_files(tmp_path, monkeypatch):
    monkeypatch.setenv("NOXUS_AUDIT_DIR", str(tmp_path))
    cfg = api_core.ProviderConfig(
        provider_type="openai_compatible",
        base_url="http://127.0.0.1:9/v1",
        api_key="k",
        red_model="m",
    )
    api_core.test_provider(cfg, ["red"])
    assert list(tmp_path.iterdir()) == []


def test_provider_test_gemini_is_header_based():
    # build_provider returns a header-based Gemini client (no query-string key).
    provider, _ = api_core.build_provider(
        api_core.ProviderConfig(provider_type="gemini_native", api_key="k")
    )
    assert isinstance(provider, GeminiNativeProvider)


# --------------------------------------------------------------------------- #
# Base URL validation (clean 400 instead of urllib "unknown url type")
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("provider_type", ["openai_compatible", "local_openai_compatible"])
def test_base_url_without_scheme_is_clean_400(provider_type):
    cfg = api_core.ProviderConfig(
        provider_type=provider_type, base_url="localhost:4000/v1", api_key="k"
    )
    with pytest.raises(api_core.ApiError) as exc:
        api_core.build_provider(cfg)
    assert exc.value.status_code == 400
    assert exc.value.message == api_core.BASE_URL_SCHEME_ERROR
    assert "unknown url type" not in exc.value.message.lower()


def test_run_agent_assisted_invalid_base_url_is_400():
    s = api_core.sample_inputs()
    req = api_core.RunAssessmentRequest(
        mode="agent_assisted",
        system_prompt=s["system_prompt"],
        security_policy_yaml=s["security_policy_yaml"],
        business_context=s["business_context"],
        provider_config=api_core.ProviderConfig(
            provider_type="openai_compatible",
            base_url="localhost:4000/v1",
            api_key="k",
            red_model="m",
            judge_model="m",
            tuning_model="m",
        ),
    )
    with pytest.raises(api_core.ApiError) as exc:
        api_core.run_assessment(req)
    assert exc.value.status_code == 400
    assert exc.value.message == api_core.BASE_URL_SCHEME_ERROR


def test_provider_test_invalid_base_url_is_400():
    cfg = api_core.ProviderConfig(
        provider_type="openai_compatible", base_url="localhost:4000/v1", api_key="k"
    )
    with pytest.raises(api_core.ApiError) as exc:
        api_core.test_provider(cfg, ["red"])
    assert exc.value.status_code == 400
    assert exc.value.message == api_core.BASE_URL_SCHEME_ERROR


# --------------------------------------------------------------------------- #
# Security policy schema — clean structured error (no raw Pydantic dump)
# --------------------------------------------------------------------------- #
def test_unsupported_policy_keys_return_structured_error():
    bad = "bogus_top: true\nsensitive_data:\n  block: []\n  not_a_field: 1\n"
    req = api_core.RunAssessmentRequest(mode="deterministic", security_policy_yaml=bad)
    with pytest.raises(api_core.ApiError) as exc:
        api_core.run_assessment(req)
    e = exc.value
    assert e.status_code == 400
    assert e.code == "policy_schema"
    assert e.message == api_core.POLICY_SCHEMA_MESSAGE
    assert "bogus_top" in e.details["unsupported_keys"]
    assert "sensitive_data.not_a_field" in e.details["unsupported_keys"]
    assert set(e.details["allowed_keys"]) == {
        "sensitive_data",
        "prompt_injection",
        "output_policy",
        "human_review",
    }
    assert "sensitive_data" in e.details["example_yaml"]


def test_policy_schema_error_has_no_raw_pydantic_dump():
    bad = "bogus_top: true\n"
    req = api_core.RunAssessmentRequest(mode="deterministic", security_policy_yaml=bad)
    with pytest.raises(api_core.ApiError) as exc:
        api_core.run_assessment(req)
    blob = json.dumps([exc.value.message, exc.value.details]).lower()
    assert "pydantic" not in blob
    assert "extra inputs are not permitted" not in blob
    assert "errors.pydantic.dev" not in blob


# --------------------------------------------------------------------------- #
# Top-level summary aliases (non-breaking flat convenience view)
# --------------------------------------------------------------------------- #
_ALIAS_KEYS = (
    "readiness_state", "before_score", "after_score", "patch_count",
    "open_risk_count", "finding_count", "tuning_iterations", "evidence_basis",
    "failed_stage", "failed_role",
)


def test_assessment_response_has_top_level_summary_aliases():
    _report, resp = api_core.run_assessment(_det_request())
    for key in _ALIAS_KEYS:
        assert key in resp, f"missing top-level alias {key!r}"
    # Nested shapes are preserved, not replaced.
    assert "readiness" in resp and "metadata" in resp and "report" in resp


def test_top_level_aliases_match_nested_report_values():
    _report, resp = api_core.run_assessment(_det_request())
    rep = resp["report"]
    assert resp["readiness_state"] == rep["readiness_state"]
    assert resp["before_score"] == rep["before_score"] == resp["readiness"]["before_score"]
    assert resp["after_score"] == rep["after_score"] == resp["readiness"]["after_score"]
    assert resp["patch_count"] == len(rep["patch_operations_applied"])
    assert resp["open_risk_count"] == len(rep["open_risks"])
    assert resp["finding_count"] == sum(len(r["findings"]) for r in rep["after_results"])
    assert resp["tuning_iterations"] == resp["metadata"]["tuning_iterations"]
    assert resp["evidence_basis"] == resp["metadata"]["evidence_basis"]
    # Honest: deterministic sample is CONDITIONAL_PASS with an open risk, not PASS.
    assert resp["readiness_state"] == "CONDITIONAL_PASS"
    assert resp["open_risk_count"] >= 1


def test_top_level_aliases_do_not_include_api_key():
    provider = FakeLLMProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.EMPTY_PATCHSET,
    )
    report = run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
    )
    cfg = api_core.ProviderConfig(
        provider_type="gemini_native", api_key=_SENTINEL_KEY,
        red_model="rm", judge_model="jm", tuning_model="tm",
    )
    resp = api_core.build_assessment_response(
        report, mode="agent_assisted", provider_config=cfg
    )
    alias_blob = json.dumps({k: resp[k] for k in _ALIAS_KEYS})
    assert _SENTINEL_KEY not in alias_blob
    # Alias values are plain scalars (str/int/None), never nested provider config.
    for k in _ALIAS_KEYS:
        assert resp[k] is None or isinstance(resp[k], (str, int))
