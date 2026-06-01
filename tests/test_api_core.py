"""Tests for the framework-free API core (no FastAPI needed to run these).

Covers the deterministic assessment contract, agent-assisted config validation,
provider construction, API-key redaction/non-echo, and audit export.
"""

import json
from pathlib import Path

import pytest

import m2_data
from noxus import api_core
from noxus.llm_provider import GeminiNativeProvider, LiteLLMProvider

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


def test_agent_assisted_run_does_not_echo_key_on_provider_failure():
    # Unreachable endpoint -> ProviderError -> ApiError(502), key never surfaced.
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
    with pytest.raises(api_core.ApiError) as exc:
        api_core.run_assessment(req)
    assert _SENTINEL_KEY not in exc.value.message


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
