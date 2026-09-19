#!/usr/bin/env python3


from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

REQUIRED = [
    "NOXUS_LLM_BASE_URL",
    "NOXUS_LLM_API_KEY",
    "NOXUS_RED_MODEL",
    "NOXUS_JUDGE_MODEL",
    "NOXUS_TUNING_MODEL",
]

API_BASE = os.environ.get("NOXUS_API_BASE_URL", "http://127.0.0.1:8787").rstrip("/")
API_KEY = os.environ.get("NOXUS_LLM_API_KEY", "")


def redact(text: object) -> str:

    s = str(text)
    if API_KEY:
        s = s.replace(API_KEY, "***REDACTED***")
    return s


def fail(code: int, msg: str) -> None:
    print(f"ERROR: {redact(msg)}", file=sys.stderr)
    raise SystemExit(code)


def post(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            fail(4, f"HTTP {exc.code} from {path} with unparseable body")
    except urllib.error.URLError as exc:
        fail(3, f"API unreachable at {API_BASE}{path}: {exc.reason}")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        fail(4, f"malformed JSON from {path}: {exc}")


def get(path: str) -> dict:
    try:
        with urllib.request.urlopen(API_BASE + path, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        fail(3, f"API unreachable at {API_BASE}{path}: {getattr(exc, 'reason', exc)}")
    except json.JSONDecodeError as exc:
        fail(4, f"malformed JSON from {path}: {exc}")


def main() -> int:
    profile_name = os.environ.get("NOXUS_PROVIDER_PROFILE")
    missing = [] if profile_name else [v for v in REQUIRED if not os.environ.get(v)]
    if missing:
        fail(2, f"missing required env vars: {', '.join(missing)}")

    health = get("/api/health")
    if not health.get("ok"):
        fail(3, "API /api/health did not report ok")

    selection = (
        {"provider_profile": profile_name}
        if profile_name
        else {
            "provider_config": {
                "provider_type": "local_openai_compatible",
                "base_url": os.environ["NOXUS_LLM_BASE_URL"],
                "api_key": API_KEY,
                "red_model": os.environ["NOXUS_RED_MODEL"],
                "judge_model": os.environ["NOXUS_JUDGE_MODEL"],
                "tuning_model": os.environ["NOXUS_TUNING_MODEL"],
            }
        }
    )

    print("== Provider diagnostics (per-role schema contract) ==")
    diag = post(
        "/api/providers/test",
        {
            **selection,
            "models_to_test": ["red", "judge", "tuning"],
        },
    )
    results = diag.get("results")
    if not isinstance(results, list):
        fail(4, "provider test response missing 'results'")
    print(f"  overall ok: {diag.get('ok')}  ({diag.get('provider_type')})")
    for r in results:
        print(
            f"  - {r.get('role', ''):6} ok={r.get('ok')} "
            f"validated={r.get('response_validated')} {r.get('latency_ms')}ms "
            f":: {redact(r.get('message', ''))}"
        )

    print()
    print("== Agent-Assisted assessment run ==")
    si = get("/api/sample-inputs")
    run = post(
        "/api/assessments/run",
        {
            "mode": "agent_assisted",
            "system_prompt": si.get("system_prompt", ""),
            "security_policy_yaml": si.get("security_policy_yaml", ""),
            "business_context": si.get("business_context", ""),
            **selection,
        },
    )
    if "detail" in run and "readiness" not in run:
        print(f"  run returned API error: {redact(run['detail'])}")
        return 0

    try:
        red = run["red_blue"]["red"]
        baseline = len(red["baseline_probes"])
        findings = red["before_summary"]["findings"]
        patches = len(run["red_blue"]["blue"]["patches"])
        state = run["readiness"]["badge"]["state"]
        iters = run["metadata"]["tuning_iterations"]
        open_risks = bool(run.get("report", {}).get("open_risks"))
        rail = bool(run.get("report", {}).get("after_system_prompt"))
        sf = run.get("schema_failure")
    except (KeyError, TypeError) as exc:
        fail(4, f"run response missing expected fields: {exc}")

    failed = f"{sf['failed_role']} ({sf.get('failed_stage')})" if sf else "none"
    print(f"  final readiness    : {state}")
    print(f"  tuning iterations  : {iters}")
    print(f"  failed stage/role  : {failed}")
    print(f"  baseline probes    : {baseline}")
    print(f"  baseline findings  : {findings}")
    print(f"  patches applied    : {patches}")
    print(f"  safety-rail telem. : {rail}")
    print(f"  open risks present : {open_risks}")

    print()
    print("Done. (API key was never printed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
