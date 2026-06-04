"""Release hygiene: test-count consistency across Dockerfile/docs/frontend/proof,
and physical-artifact cleanup (no tracked venv/node_modules/dist/.claude/.env).

These are STATIC checks (read files / git index / pure proof payload); they never
build Docker, hit the network, or start a server.

The single source of truth for the Python release count is the Dockerfile env
``NOXUS_TEST_COUNT`` (which /api/proof echoes); the frontend count is parsed from
the README. Every other surface must agree with these — so the only manual edit
when the count changes is the metadata itself, not these tests.
"""

import re
import subprocess
from pathlib import Path

import pytest

from noxus import api_core

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"
README = PROJECT_ROOT / "README.md"
DOCS_DIR = PROJECT_ROOT / "docs"
TOP_HEADER = PROJECT_ROOT / "apps" / "web" / "src" / "components" / "TopHeader.tsx"
SAFEGUARDS = PROJECT_ROOT / "apps" / "web" / "src" / "components" / "EngineeringSafeguards.tsx"

DOC_FILES = [README] + sorted(DOCS_DIR.glob("*.md"))

# Counts that were stale in earlier passes — they must not appear as a CURRENT
# release-proof claim anywhere (Dockerfile/docs/frontend chips).
STALE_COUNT_CLAIMS = (
    "201 passing", "201 automated", "201 passed", "201 Python", "201 tests",
    "NOXUS_TEST_COUNT=201", "27 Vitest", "27 frontend tests", "27 tests",
    "285 passing", "285 automated", "285 passed", "285 Python", "285 tests",
    "NOXUS_TEST_COUNT=285", "33 Vitest", "33 frontend tests", "33 tests",
)


def _dockerfile_py_count() -> int:
    m = re.search(r"NOXUS_TEST_COUNT=(\d+)", DOCKERFILE.read_text(encoding="utf-8"))
    assert m, "Dockerfile must declare NOXUS_TEST_COUNT"
    return int(m.group(1))


def _readme_py_count() -> int:
    m = re.search(r"(\d+) Python tests", README.read_text(encoding="utf-8"))
    assert m, "README must state '<N> Python tests'"
    return int(m.group(1))


def _readme_fe_count() -> int:
    m = re.search(r"(\d+) frontend tests", README.read_text(encoding="utf-8"))
    assert m, "README must state '<N> frontend tests'"
    return int(m.group(1))


# --------------------------------------------------------------------------- #
# Test-count consistency
# --------------------------------------------------------------------------- #
def test_dockerfile_test_count_matches_docs():
    assert _dockerfile_py_count() == _readme_py_count()


def test_frontend_proof_count_matches_docs_or_declared_release_count():
    py = _dockerfile_py_count()
    fe = _readme_fe_count()
    header = TOP_HEADER.read_text(encoding="utf-8")
    m = re.search(r"proof\?\.test_count\s*\?\?\s*(\d+)", header)
    assert m, "TopHeader must declare a fallback proof test_count"
    assert int(m.group(1)) == py, "TopHeader proof fallback must match the release count"
    assert f"{fe} frontend tests" in header, "TopHeader frontend chip must match docs"
    safeguards = SAFEGUARDS.read_text(encoding="utf-8")
    assert f"{py} Python + {fe} frontend tests" in safeguards


def test_docs_do_not_contain_stale_test_counts_285_or_33():
    py, fe = _dockerfile_py_count(), _readme_fe_count()
    surfaces = DOC_FILES + [TOP_HEADER, SAFEGUARDS, DOCKERFILE]
    for path in surfaces:
        text = path.read_text(encoding="utf-8")
        for s in STALE_COUNT_CLAIMS:
            # Only flag a stale claim if it is NOT the genuine current count.
            if str(py) in s or f"{fe} frontend" in s:
                continue
            assert s not in text, f"{path.name} has a stale test-count claim: {s!r}"


def test_docs_contain_current_final_test_counts():
    py, fe = _dockerfile_py_count(), _readme_fe_count()
    readme = README.read_text(encoding="utf-8")
    assert f"{py} Python tests" in readme
    assert f"{fe} frontend tests" in readme
    assert "Release verification" in readme
    # Never imply runtime/dynamic counting.
    assert "live test count" not in readme.lower()
    # The submission/demo/challenge docs reference the current Python count.
    for name in ("submission-checklist.md", "challenge-application-draft.md", "demo-script.md"):
        text = (DOCS_DIR / name).read_text(encoding="utf-8")
        assert str(py) in text, f"{name} must reference the current Python count {py}"


def test_api_proof_count_matches_release_metadata():
    # /api/proof echoes the configured release count (NOXUS_TEST_COUNT). The proof
    # payload builder must pass it through unchanged, and the declared metadata
    # (Dockerfile) must equal the docs — so proof/docs/Docker all agree.
    py = _dockerfile_py_count()
    payload = api_core.proof_indicators(test_count=py)
    assert payload["test_count"] == py
    assert py == _readme_py_count()


# --------------------------------------------------------------------------- #
# Physical-artifact cleanup / .dockerignore coverage
# --------------------------------------------------------------------------- #
def _git_tracked_files():
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("git not available / not a git repo")
    return out.stdout.splitlines()


def test_no_tracked_venv_or_scratch_artifacts():
    tracked = _git_tracked_files()
    offenders = [
        f
        for f in tracked
        if re.search(r"(^|/)\.venv", f)
        or "venv-review" in f
        or "venv-agent" in f
        or "venv-final" in f
        or "venv-micro" in f
        or re.search(r"(^|/)node_modules/", f)
        or re.search(r"(^|/)dist/", f)
        or re.search(r"(^|/)\.claude/", f)
        or re.search(r"(^|/)screenshots/", f)
        or f == ".env"
        or f.endswith("/.env")
    ]
    assert not offenders, f"scratch/build artifacts are tracked in git: {offenders}"


def test_dockerignore_excludes_release_artifacts():
    text = DOCKERIGNORE.read_text(encoding="utf-8")
    required = (
        ".venv",
        ".venv*/",
        "node_modules",
        "apps/web/node_modules/",
        "apps/web/dist/",
        ".claude/",
        "screenshots/",
        ".env",
    )
    for needle in required:
        assert needle in text, f".dockerignore must exclude {needle!r}"
