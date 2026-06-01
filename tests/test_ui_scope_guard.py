"""Scope guard: web-framework isolation + dependency hygiene.

Static analysis only — no imports of production UI code, no browser, no server.

After the React/FastAPI replacement:
- Streamlit is fully removed from the runtime (no module may import it).
- FastAPI/uvicorn are the new runtime web deps, isolated to ``api_server.py``.
- ``api_core.py`` stays framework-free (no fastapi/uvicorn/streamlit) so it is
  fully unit-testable without a web server.
- ``ui_formatters.py`` stays free of any view-framework reference.
- No cloud/provider SDKs are ever added.
"""

import ast
import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src" / "noxus"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
UI_FORMATTERS = SRC_DIR / "ui_formatters.py"
API_CORE = SRC_DIR / "api_core.py"
API_SERVER = SRC_DIR / "api_server.py"
WEB_SRC = PROJECT_ROOT / "apps" / "web" / "src"

# The only file permitted to import the web framework.
ALLOWED_WEB_FRAMEWORK_FILE = "api_server.py"

ALLOWED_RUNTIME_DEPENDENCIES = {"pydantic", "PyYAML", "fastapi", "uvicorn"}

FORBIDDEN_DEPENDENCIES = {
    "vertexai",
    "google-cloud",
    "google.cloud",
    "google-cloud-bigquery",
    "google-cloud-storage",
    "langgraph",
    "streamlit",
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


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def _imports_any(modules: set[str], roots: set[str]) -> bool:
    return any(
        m == root or m.startswith(root + ".") for m in modules for root in roots
    )


def test_streamlit_is_fully_removed_from_runtime():
    """No source module may import streamlit — the UI is React now."""
    offenders = [
        path.name
        for path in sorted(SRC_DIR.rglob("*.py"))
        if _imports_any(_imported_modules(path), {"streamlit"})
    ]
    assert not offenders, f"streamlit still imported in: {offenders}"
    # And the Streamlit app module itself is gone.
    assert not (SRC_DIR / "ui_streamlit.py").exists()


def test_web_framework_import_is_isolated_to_api_server():
    """fastapi/uvicorn may only be imported by api_server.py."""
    web_roots = {"fastapi", "uvicorn", "starlette"}
    offenders = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        if path.name == ALLOWED_WEB_FRAMEWORK_FILE:
            continue
        if _imports_any(_imported_modules(path), web_roots):
            offenders.append(path.name)
    assert not offenders, f"web framework imported outside api_server.py: {offenders}"
    # api_server.py genuinely imports fastapi.
    assert _imports_any(_imported_modules(API_SERVER), {"fastapi"})


def test_api_core_is_framework_free():
    """api_core stays pure: no fastapi/uvicorn/streamlit imports or references."""
    source = API_CORE.read_text(encoding="utf-8").lower()
    for token in ("fastapi", "uvicorn", "streamlit"):
        assert token not in source, f"api_core must not reference {token}"
    assert not _imports_any(
        _imported_modules(API_CORE), {"fastapi", "uvicorn", "streamlit", "starlette"}
    )


def test_core_modules_do_not_import_forbidden_dependencies():
    forbidden_roots = {
        "streamlit",
        "requests",
        "httpx",
        "openai",
        "anthropic",
        "boto3",
        "vertexai",
        "langgraph",
        "google",  # covers google.cloud / google.generativeai / google.genai
    }
    for path in sorted(SRC_DIR.rglob("*.py")):
        offending = {
            m
            for m in _imported_modules(path)
            for root in forbidden_roots
            if m == root or m.startswith(root + ".")
        }
        assert not offending, f"{path.name} imports forbidden modules: {offending}"


def test_pyproject_runtime_dependencies_are_allowed_only():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    names = {re.split(r"[<>=!~ ]", d, 1)[0].strip() for d in deps}
    assert "fastapi" in names
    assert "uvicorn" in names
    assert "streamlit" not in names
    assert names <= ALLOWED_RUNTIME_DEPENDENCIES, (
        f"unexpected runtime dependencies: {names - ALLOWED_RUNTIME_DEPENDENCIES}"
    )
    assert not (names & FORBIDDEN_DEPENDENCIES)


def test_ui_formatters_has_no_view_framework_references():
    source = UI_FORMATTERS.read_text(encoding="utf-8").lower()
    for token in ("streamlit", "fastapi", "react"):
        assert token not in source, f"ui_formatters must stay framework-free ({token})"
    assert not _imports_any(
        _imported_modules(UI_FORMATTERS), {"streamlit", "fastapi", "uvicorn"}
    )
    # And it imports without pulling in a web framework.
    import sys

    import noxus.ui_formatters  # noqa: F401

    assert "streamlit" not in sys.modules


def test_gemini_provider_uses_stdlib_urllib_and_header_key():
    """GeminiNativeProvider must use stdlib urllib and a header-based API key."""
    src = (SRC_DIR / "llm_provider.py").read_text(encoding="utf-8")
    modules = _imported_modules(SRC_DIR / "llm_provider.py")
    assert any(m == "urllib" or m.startswith("urllib.") for m in modules)
    # No SDKs / requests / httpx in the provider module.
    assert not _imports_any(
        modules, {"requests", "httpx", "openai", "google", "anthropic"}
    )
    # The Gemini key travels in a request header, not the URL query string.
    assert "x-goog-api-key" in src
    assert "?key=" not in src


def test_frontend_does_not_persist_api_keys():
    """No localStorage/sessionStorage usage in the React app (keys are in-memory).

    Test files under src/test/ are excluded — they legitimately read web storage
    only to ASSERT it stays empty.
    """
    if not WEB_SRC.is_dir():
        return  # frontend not present in this checkout
    test_dir = WEB_SRC / "test"
    offenders = []
    for path in sorted(WEB_SRC.rglob("*.ts*")):
        if test_dir in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        if "localStorage" in text or "sessionStorage" in text:
            offenders.append(path.name)
    assert not offenders, f"frontend must not use web storage: {offenders}"


def test_frontend_api_key_field_is_password():
    """The provider settings panel renders the API key as a password input."""
    panel = WEB_SRC / "components" / "ProviderSettings.tsx"
    if not panel.exists():
        return
    text = panel.read_text(encoding="utf-8")
    assert 'type={showKey ? "text" : "password"}' in text
