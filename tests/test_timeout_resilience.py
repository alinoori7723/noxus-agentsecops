import json

import m2_data
import pytest

from noxus import api_core
from noxus.llm_provider import (
    ProviderAuthError,
    ProviderError,
    ProviderTimeoutError,
)
from noxus.llm_runtime import (
    RoleBoundProvider,
    RoleProviderError,
    RoleTimeoutError,
    TimeoutConfig,
    tuning_fallback_model_from_env,
)
from noxus.orchestrator import run_readiness_assessment
from noxus.schemas import ReadinessState

SENTINEL_KEY = "sk-LIVE-SECRET-DO-NOT-LEAK-1234567890"
PRIMARY_TUNING = "gemini-3.1-pro-preview"
FALLBACK_TUNING = "gemini-3.5-flash"


FAST = TimeoutConfig(
    red=180, judge=180, tuning=240, provider_test=60, max_retries=0, backoff_seconds=0.0
)


class FlakyProvider:
    def __init__(
        self,
        *,
        red=None,
        judge=None,
        tuning=None,
        repair=None,
        default=None,
        timeout_roles=(),
        timeout_models=(),
        auth_roles=(),
        max_timeouts=None,
    ):
        self.responses = {
            "red": red,
            "judge": judge,
            "tuning": tuning,
            "repair": repair,
            "default": default,
        }
        self.timeout_roles = set(timeout_roles)
        self.timeout_models = set(timeout_models)
        self.auth_roles = set(auth_roles)
        self.max_timeouts = dict(max_timeouts) if max_timeouts else None
        self.calls = []
        self._timeout_counts = {}

    @staticmethod
    def _role(system_prompt):
        if "[NOXUS_REPAIR]" in system_prompt:
            return "repair"
        if "[NOXUS_RED_TEAM]" in system_prompt:
            return "red"
        if "[NOXUS_JUDGE]" in system_prompt:
            return "judge"
        if "[NOXUS_TUNING]" in system_prompt:
            return "tuning"
        return "default"

    def complete(
        self, *, model, system_prompt, user_prompt, json_schema_instruction=None, timeout=None
    ):
        role = self._role(system_prompt)
        self.calls.append({"role": role, "model": model, "timeout": timeout})
        if role in self.auth_roles:
            raise ProviderAuthError("Authentication failed at LLM endpoint: 401 Unauthorized")
        if role in self.timeout_roles or model in self.timeout_models:
            n = self._timeout_counts.get(role, 0)
            limit = None if self.max_timeouts is None else self.max_timeouts.get(role)
            if limit is None or n < limit:
                self._timeout_counts[role] = n + 1
                raise ProviderTimeoutError("LLM request timed out.")
        resp = self.responses.get(role) or self.responses.get("default")
        if resp is None:
            raise ProviderError(f"FlakyProvider: no response for role {role}")
        return resp


def _run(
    provider,
    *,
    timeout_config=FAST,
    tuning_fallback_model=None,
    provider_type="gemini_native",
    red_model="gemini-3.5-flash",
    judge_model="gemini-3.5-flash",
):
    return run_readiness_assessment(
        system_prompt=m2_data.SAMPLE_SYSTEM_PROMPT,
        policy=m2_data.SAMPLE_POLICY,
        business_context_text=m2_data.SAMPLE_BUSINESS_CONTEXT,
        mode="agent_assisted",
        provider=provider,
        red_model=red_model,
        judge_model=judge_model,
        tuning_model=PRIMARY_TUNING,
        timeout_config=timeout_config,
        tuning_fallback_model=tuning_fallback_model,
        provider_type=provider_type,
    )


def test_default_timeout_values_are_used():
    cfg = TimeoutConfig.from_env({})
    assert cfg.red == 180 and cfg.judge == 180
    assert cfg.tuning == 240
    assert cfg.provider_test == 60
    assert cfg.max_retries == 2
    assert cfg.backoff_seconds == 1.5


def test_role_specific_timeout_overrides_global_timeout():
    env = {"NOXUS_LLM_TIMEOUT_SECONDS": "100", "NOXUS_TUNING_TIMEOUT_SECONDS": "300"}
    cfg = TimeoutConfig.from_env(env)
    assert cfg.red == 100 and cfg.judge == 100
    assert cfg.tuning == 300
    assert cfg.timeout_for("tuning") == 300
    assert cfg.timeout_for("red") == 100


def test_provider_test_timeout_is_shorter_by_default():
    cfg = TimeoutConfig.from_env({})
    assert cfg.provider_test < cfg.red
    assert cfg.provider_test < cfg.tuning


def test_role_timeout_is_applied_to_provider_call():

    provider = FlakyProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.EMPTY_PATCHSET,
    )
    cfg = TimeoutConfig(
        red=33, judge=44, tuning=55, provider_test=60, max_retries=0, backoff_seconds=0.0
    )
    _run(provider, timeout_config=cfg)
    red_calls = [c for c in provider.calls if c["role"] == "red"]
    tuning_calls = [c for c in provider.calls if c["role"] == "tuning"]
    assert red_calls and all(c["timeout"] == 33 for c in red_calls)
    assert all(c["timeout"] == 55 for c in tuning_calls)


class _AlwaysTimeout:
    def __init__(self):
        self.calls = 0

    def complete(
        self, *, model, system_prompt, user_prompt, json_schema_instruction=None, timeout=None
    ):
        self.calls += 1
        raise ProviderTimeoutError("LLM request timed out.")


def test_timeout_retried_up_to_configured_limit():
    inner = _AlwaysTimeout()
    delays = []
    rb = RoleBoundProvider(
        inner,
        role="tuning",
        provider_type="gemini_native",
        timeout=240,
        max_retries=2,
        backoff_seconds=1.5,
        sleep=delays.append,
        jitter=lambda base: 0.0,
    )
    with pytest.raises(RoleTimeoutError):
        rb.complete(model="m", system_prompt="[NOXUS_TUNING]", user_prompt="x")

    assert inner.calls == 3

    assert delays == [1.5, 3.0]


def test_retry_count_reported():
    inner = _AlwaysTimeout()
    rb = RoleBoundProvider(
        inner,
        role="red",
        provider_type="gemini_native",
        timeout=180,
        max_retries=2,
        backoff_seconds=0.0,
        sleep=lambda s: None,
    )
    with pytest.raises(RoleTimeoutError) as exc:
        rb.complete(model="m", system_prompt="[NOXUS_RED_TEAM]", user_prompt="x")
    assert exc.value.retry_count == 2
    assert exc.value.diagnostics()["retry_count"] == 2
    assert rb.retry_count == 2


def test_schema_contract_error_not_retried():

    class _BadOnce:
        def __init__(self):
            self.calls = 0

        def complete(self, **kw):
            self.calls += 1
            raise ProviderError("Malformed response from LLM endpoint.")

    inner = _BadOnce()
    rb = RoleBoundProvider(
        inner,
        role="tuning",
        provider_type="gemini_native",
        timeout=240,
        max_retries=2,
        backoff_seconds=0.0,
    )
    with pytest.raises(RoleProviderError):
        rb.complete(model="m", system_prompt="[NOXUS_TUNING]", user_prompt="x")
    assert inner.calls == 1


def test_auth_error_not_retried():
    class _Auth:
        def __init__(self):
            self.calls = 0

        def complete(self, **kw):
            self.calls += 1
            raise ProviderAuthError("Authentication failed at LLM endpoint: 401")

    inner = _Auth()
    rb = RoleBoundProvider(
        inner,
        role="judge",
        provider_type="gemini_native",
        timeout=180,
        max_retries=2,
        backoff_seconds=0.0,
    )
    with pytest.raises(RoleProviderError) as exc:
        rb.complete(model="m", system_prompt="[NOXUS_JUDGE]", user_prompt="x")
    assert inner.calls == 1

    assert not isinstance(exc.value, RoleTimeoutError)


def test_no_api_key_leak_in_retry_logs():

    class _LeakyTimeout:
        def complete(self, **kw):
            raise ProviderTimeoutError(f"timed out; Authorization: Bearer {SENTINEL_KEY}")

    rb = RoleBoundProvider(
        _LeakyTimeout(),
        role="tuning",
        provider_type="gemini_native",
        timeout=240,
        max_retries=1,
        backoff_seconds=0.0,
        sleep=lambda s: None,
    )
    with pytest.raises(RoleTimeoutError) as exc:
        rb.complete(model="m", system_prompt="[NOXUS_TUNING]", user_prompt="x")
    assert SENTINEL_KEY not in exc.value.safe_message
    assert SENTINEL_KEY not in json.dumps(exc.value.diagnostics())


def _red_timeout_provider():
    return FlakyProvider(
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.PATCHSET_WITH_RAIL,
        timeout_roles=("red",),
    )


def test_timeout_error_includes_failed_role():
    report = _run(_red_timeout_provider())
    assert report.metadata.timeout_failed_role == "red"
    assert report.metadata.timeout_fatal is True
    resp = api_core.build_assessment_response(report, mode="agent_assisted")
    assert resp["timeout_failure"]["failed_role"] == "red"


def test_timeout_error_includes_model_and_provider():
    report = _run(_red_timeout_provider())
    resp = api_core.build_assessment_response(
        report,
        mode="agent_assisted",
        provider_config=api_core.ProviderConfig(provider_type="gemini_native"),
    )
    tf = resp["timeout_failure"]
    assert tf["model"] == "gemini-3.5-flash"
    assert tf["provider_type"] == "gemini_native"
    assert tf["timeout_seconds"] == 180
    assert "Red Team Agent" in tf["message"]


def test_timeout_error_does_not_echo_api_key():

    cfg = api_core.ProviderConfig(
        provider_type="openai_compatible",
        base_url="http://127.0.0.1:9/v1",
        api_key=SENTINEL_KEY,
        red_model="m",
        judge_model="m",
        tuning_model="m",
    )
    import os

    os.environ["NOXUS_LLM_MAX_RETRIES"] = "0"
    os.environ["NOXUS_LLM_RETRY_BACKOFF_SECONDS"] = "0"
    try:
        s = api_core.sample_inputs()
        req = api_core.RunAssessmentRequest(
            mode="agent_assisted",
            system_prompt=s["system_prompt"],
            security_policy_yaml=s["security_policy_yaml"],
            business_context=s["business_context"],
            provider_config=cfg,
        )
        try:
            _r, resp = api_core.run_assessment(req)
            assert SENTINEL_KEY not in json.dumps(resp)
        except api_core.ApiError as exc:
            assert SENTINEL_KEY not in exc.message
            assert SENTINEL_KEY not in json.dumps(exc.details)
    finally:
        del os.environ["NOXUS_LLM_MAX_RETRIES"]
        del os.environ["NOXUS_LLM_RETRY_BACKOFF_SECONDS"]


def test_ui_payload_carries_role_specific_timeout_message():

    report = _run(_red_timeout_provider())
    resp = api_core.build_assessment_response(report, mode="agent_assisted")
    assert "timed out during Red Team Agent" in resp["timeout_failure"]["message"]


def test_tuning_fallback_model_from_env():
    assert tuning_fallback_model_from_env({}) is None
    assert (
        tuning_fallback_model_from_env({"NOXUS_TUNING_FALLBACK_MODEL": "gemini-3.5-flash"})
        == "gemini-3.5-flash"
    )


def test_tuning_timeout_uses_configured_fallback_model():

    provider = FlakyProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.PATCHSET_WITH_RAIL,
        timeout_models=(PRIMARY_TUNING,),
    )
    report = _run(provider, tuning_fallback_model=FALLBACK_TUNING)
    tuning_models = {c["model"] for c in provider.calls if c["role"] == "tuning"}
    assert PRIMARY_TUNING in tuning_models and FALLBACK_TUNING in tuning_models
    assert report.metadata.tuning_fallback_used is True
    assert report.metadata.tuning_fallback_model == FALLBACK_TUNING


def test_tuning_fallback_is_reported_in_trace():
    provider = FlakyProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.PATCHSET_WITH_RAIL,
        timeout_models=(PRIMARY_TUNING,),
    )
    report = _run(provider, tuning_fallback_model=FALLBACK_TUNING)
    resp = api_core.build_assessment_response(
        report,
        mode="agent_assisted",
        provider_config=api_core.ProviderConfig(
            provider_type="gemini_native", tuning_model=PRIMARY_TUNING
        ),
    )
    assert resp["tuning_fallback"]["used"] is True
    assert resp["tuning_fallback"]["original_model"] == PRIMARY_TUNING
    assert resp["tuning_fallback"]["fallback_model"] == FALLBACK_TUNING
    assert resp["tuning_fallback"]["reason"] == "timeout"
    assert resp["agent_trace"]["tuning_fallback_used"] is True


def test_fallback_failure_returns_human_review_required_with_baseline():

    provider = FlakyProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        timeout_models=(PRIMARY_TUNING, FALLBACK_TUNING),
    )
    report = _run(
        provider,
        tuning_fallback_model=FALLBACK_TUNING,
        red_model="red-model-x",
        judge_model="judge-model-x",
    )
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    assert report.before_results, "deterministic baseline must be preserved"
    assert report.metadata.timeout_failed_role == "tuning"
    assert report.metadata.timeout_fatal is True


def test_fallback_does_not_hide_original_timeout():
    provider = FlakyProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.PATCHSET_WITH_RAIL,
        timeout_models=(PRIMARY_TUNING,),
    )
    report = _run(provider, tuning_fallback_model=FALLBACK_TUNING)

    assert report.metadata.timeout_failed_role == "tuning"
    assert report.metadata.timeout_fatal is False
    assert report.metadata.tuning_fallback_original_model == PRIMARY_TUNING
    assert report.metadata.tuning_fallback_model == FALLBACK_TUNING


def test_red_timeout_preserves_baseline_and_reports_role():
    report = _run(_red_timeout_provider())
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    assert report.before_results and any(r.findings for r in report.before_results)
    assert report.metadata.timeout_failed_role == "red"

    assert report.patch_operations_applied == []
    assert report.readiness_state is not ReadinessState.PASS


def test_judge_timeout_preserves_red_and_baseline_trace():

    provider = FlakyProvider(
        red=m2_data.VALID_PROBE_BATCH, tuning=m2_data.PATCHSET_WITH_RAIL, timeout_roles=("judge",)
    )
    report = _run(provider)

    assert report.before_results
    assert report.metadata.red_team_status == "used"
    assert report.metadata.timeout_failed_role == "judge"
    assert report.metadata.timeout_fatal is False
    resp = api_core.build_assessment_response(report, mode="agent_assisted")
    assert resp["timeout_failure"]["failed_role"] == "judge"
    assert resp["timeout_failure"]["fatal"] is False


def test_tuning_timeout_preserves_baseline_and_prior_trace():

    provider = FlakyProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        timeout_models=(PRIMARY_TUNING,),
    )
    report = _run(provider)
    assert report.readiness_state is ReadinessState.HUMAN_REVIEW_REQUIRED
    assert report.before_results
    assert report.metadata.timeout_failed_role == "tuning"

    assert report.metadata.red_team_status == "used"


def test_no_blank_timeline_on_llm_timeout_after_baseline():
    report = _run(_red_timeout_provider())
    resp = api_core.build_assessment_response(report, mode="agent_assisted")

    assert resp["timeline"], "timeline must not be empty"
    assert resp["red_blue"]["red"]["baseline_probes"]
    assert resp["agent_trace"]["baseline_probe_count"] > 0


def test_no_fake_patch_on_timeout():
    for provider in (
        _red_timeout_provider(),
        FlakyProvider(
            red=m2_data.VALID_PROBE_BATCH,
            judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
            timeout_models=(PRIMARY_TUNING,),
        ),
    ):
        report = _run(provider)
        assert report.patch_operations_applied == []
        assert report.after_score == 0
        assert report.readiness_state is not ReadinessState.PASS


def _provider_test(provider_type, role_provider, monkeypatch):

    cfg = api_core.ProviderConfig(provider_type="gemini_native", api_key=SENTINEL_KEY)
    monkeypatch.setattr(
        api_core, "build_provider", lambda c: (role_provider, dict(api_core.DEFAULT_MODELS))
    )
    return api_core.test_provider(cfg, ["red", "judge", "tuning"])


def test_provider_test_reports_latency_per_role(monkeypatch):
    provider = FlakyProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.PATCHSET_WITH_RAIL,
        default=m2_data.VALID_PROBE_BATCH,
    )
    out = _provider_test("gemini_native", provider, monkeypatch)
    assert {r["role"] for r in out["results"]} == {"red", "judge", "tuning"}
    for r in out["results"]:
        assert isinstance(r["latency_ms"], int) and r["latency_ms"] >= 0


def test_provider_test_distinguishes_timeout_from_schema_failure(monkeypatch):

    provider = FlakyProvider(
        judge='{"not":"a judgment"}', tuning=m2_data.PATCHSET_WITH_RAIL, timeout_roles=("red",)
    )
    out = _provider_test("gemini_native", provider, monkeypatch)
    by_role = {r["role"]: r for r in out["results"]}
    assert by_role["red"]["error_type"] == "timeout"
    assert by_role["red"]["timed_out"] is True
    assert by_role["judge"]["error_type"] == "schema"
    assert by_role["judge"]["timed_out"] is False


def test_provider_test_does_not_store_api_key(monkeypatch):
    provider = FlakyProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.PATCHSET_WITH_RAIL,
    )
    out = _provider_test("gemini_native", provider, monkeypatch)
    assert SENTINEL_KEY not in json.dumps(out)


def test_provider_test_does_not_write_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("NOXUS_AUDIT_DIR", str(tmp_path))
    provider = FlakyProvider(
        red=m2_data.VALID_PROBE_BATCH,
        judge=m2_data.VALID_JUDGMENT_NO_VIOLATION,
        tuning=m2_data.PATCHSET_WITH_RAIL,
        timeout_roles=("red",),
    )
    _provider_test("gemini_native", provider, monkeypatch)

    assert list(tmp_path.iterdir()) == []
