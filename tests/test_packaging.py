import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

ALLOWED_RUNTIME_DEPENDENCIES = {"pydantic", "PyYAML", "streamlit"}

FORBIDDEN_DEPENDENCIES = {
    "vertexai",
    "google-cloud",
    "google.cloud",
    "google-cloud-bigquery",
    "google-cloud-storage",
    "langgraph",
    "fastapi",
    "requests",
    "httpx",
    "openai",
    "anthropic",
    "google-generativeai",
    "google.generativeai",
    "google-genai",
    "google.genai",
    "boto3",
}


def _dockerfile_lines() -> list[str]:
    return [
        line.strip()
        for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _dockerignore_entries() -> set[str]:
    return {
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def test_dockerfile_uses_python_311_slim():
    assert any(
        line.startswith("FROM python:3.11-slim") for line in _dockerfile_lines()
    )


def test_dockerfile_creates_non_root_user():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "noxus_user" in text
    assert re.search(r"\buseradd\b|\badduser\b", text)


def test_dockerfile_switches_to_non_root_user():
    user_directives = [
        line.split(None, 1)[1].strip()
        for line in _dockerfile_lines()
        if line.startswith("USER ")
    ]
    assert user_directives, "Dockerfile must set a USER"
    # The final runtime user must be the non-root user.
    assert user_directives[-1] == "noxus_user"
    assert user_directives[-1] != "root"


def test_dockerfile_starts_streamlit_by_default():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "CMD" in text
    assert "streamlit run src/noxus/ui_streamlit.py" in text


def test_dockerignore_excludes_local_artifacts():
    entries = _dockerignore_entries()
    required = {
        ".git/",
        ".venv/",
        "venv/",
        "__pycache__/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        ".coverage",
        "htmlcov/",
        "dist/",
        "build/",
        "*.egg-info/",
        "outputs/",
        "reports/",
        "tmp/",
        "*.log",
        "tests/",
        ".env",
        ".env.*",
    }
    missing = required - entries
    assert not missing, f".dockerignore missing exclusions: {missing}"


def test_dockerignore_does_not_exclude_required_source_files():
    entries = _dockerignore_entries()
    must_not_exclude = {
        "src",
        "src/",
        "pyproject.toml",
        "README.md",
        "src/noxus/samples",
        "src/noxus/samples/",
    }
    overlap = entries & must_not_exclude
    assert not overlap, f".dockerignore must not exclude required files: {overlap}"


def test_pyproject_does_not_add_forbidden_cloud_dependencies():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    names = {re.split(r"[<>=!~ ]", d, 1)[0].strip() for d in deps}
    assert names <= ALLOWED_RUNTIME_DEPENDENCIES, (
        f"unexpected runtime dependencies: {names - ALLOWED_RUNTIME_DEPENDENCIES}"
    )
    assert not (names & FORBIDDEN_DEPENDENCIES)
    # Also guard the raw text (covers optional-dependencies / extras).
    text = PYPROJECT.read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_DEPENDENCIES:
        assert forbidden not in text, f"forbidden dependency in pyproject: {forbidden}"
