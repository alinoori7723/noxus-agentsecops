import os
import subprocess
import sys
from pathlib import Path

import pytest

BASH = (
    str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe")
    if os.name == "nt"
    else "bash"
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
WRAPPER = SCRIPTS / "smoke_agent_assisted_live.sh"
PYFILE = SCRIPTS / "smoke_agent_assisted_live.py"
WRAPPER_TEXT = WRAPPER.read_text(encoding="utf-8")
PY_TEXT = PYFILE.read_text(encoding="utf-8")


def test_wrapper_exists_and_has_shebang():
    assert WRAPPER.is_file()
    assert WRAPPER_TEXT.startswith("#!/usr/bin/env bash")


def test_wrapper_is_thin_and_delegates_to_python():
    assert "set -euo pipefail" in WRAPPER_TEXT
    assert "smoke_agent_assisted_live.py" in WRAPPER_TEXT
    assert "exec python3" in WRAPPER_TEXT

    assert "<<" not in WRAPPER_TEXT
    assert 'echo "$TEST_RESP" | python3 - <<' not in WRAPPER_TEXT
    assert 'echo "$RUN_RESP" | python3 - <<' not in WRAPPER_TEXT


def test_wrapper_does_not_reference_api_key():

    assert "NOXUS_LLM_API_KEY" not in WRAPPER_TEXT
    assert "API_KEY" not in WRAPPER_TEXT


def test_wrapper_bash_syntax_is_valid():
    proc = subprocess.run([BASH, "-n", WRAPPER.as_posix()], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_python_uses_stdlib_urllib_not_requests():
    assert "import urllib.request" in PY_TEXT
    assert "import requests" not in PY_TEXT
    assert "import httpx" not in PY_TEXT


def test_python_redacts_api_key_in_output():
    assert "def redact(" in PY_TEXT
    assert "***REDACTED***" in PY_TEXT


def test_python_does_not_pass_api_key_via_argv():

    assert "os.environ" in PY_TEXT
    assert "NOXUS_LLM_API_KEY" in PY_TEXT
    assert "sys.argv" not in PY_TEXT


def test_python_checks_required_env_vars():
    for var in (
        "NOXUS_LLM_BASE_URL",
        "NOXUS_LLM_API_KEY",
        "NOXUS_RED_MODEL",
        "NOXUS_JUDGE_MODEL",
        "NOXUS_TUNING_MODEL",
    ):
        assert var in PY_TEXT
    assert "missing required env vars" in PY_TEXT


def test_python_compiles():
    import py_compile

    py_compile.compile(str(PYFILE), doraise=True)


def test_python_calls_both_endpoints():
    assert "/api/providers/test" in PY_TEXT
    assert "/api/assessments/run" in PY_TEXT


def _clean_env():
    env = dict(os.environ)
    for v in (
        "NOXUS_PROVIDER_PROFILE",
        "NOXUS_LLM_BASE_URL",
        "NOXUS_LLM_API_KEY",
        "NOXUS_RED_MODEL",
        "NOXUS_JUDGE_MODEL",
        "NOXUS_TUNING_MODEL",
    ):
        env.pop(v, None)
    return env


@pytest.mark.parametrize("runner", [[BASH], [sys.executable]])
def test_exits_2_when_required_env_missing(runner):
    target = WRAPPER if runner == [BASH] else PYFILE
    proc = subprocess.run(
        runner + [target.as_posix()], capture_output=True, text=True, env=_clean_env()
    )
    assert proc.returncode == 2
    assert "missing required env vars" in proc.stderr


def test_unreachable_api_exits_3_without_leaking_key():
    env = _clean_env()
    env.update(
        {
            "NOXUS_API_BASE_URL": "http://127.0.0.1:59996",
            "NOXUS_LLM_BASE_URL": "http://example/v1",
            "NOXUS_LLM_API_KEY": "sk-UNITTEST-SENTINEL-NOLEAK",
            "NOXUS_RED_MODEL": "m",
            "NOXUS_JUDGE_MODEL": "m",
            "NOXUS_TUNING_MODEL": "m",
        }
    )
    proc = subprocess.run([sys.executable, str(PYFILE)], capture_output=True, text=True, env=env)
    assert proc.returncode == 3
    assert "sk-UNITTEST-SENTINEL-NOLEAK" not in (proc.stdout + proc.stderr)
