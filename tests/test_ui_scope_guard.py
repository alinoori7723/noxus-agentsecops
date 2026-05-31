"""Milestone 3 scope guard: Streamlit isolation + dependency hygiene.

Static analysis only — no imports of production UI code, no browser, no server.
Streamlit is allowed solely in src/noxus/ui_streamlit.py.
"""

import ast
import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src" / "noxus"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
UI_MODULE = SRC_DIR / "ui_streamlit.py"
UI_FORMATTERS = SRC_DIR / "ui_formatters.py"

# The only file permitted to import streamlit.
ALLOWED_STREAMLIT_FILE = "ui_streamlit.py"

# Core modules that must never import streamlit.
CORE_MODULES = [
    "orchestrator.py",
    "agents.py",
    "evaluator.py",
    "patch_engine.py",
    "report.py",
    "cli.py",
    "ui_formatters.py",
    "schemas.py",
    "policy_loader.py",
    "probe_registry.py",
    "target_simulator.py",
    "patch_mapper.py",
    "json_contracts.py",
    "llm_provider.py",
    "constants.py",
]

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


def _imports_streamlit(modules: set[str]) -> bool:
    return any(m == "streamlit" or m.startswith("streamlit.") for m in modules)


def test_streamlit_import_is_isolated_to_ui_module():
    offenders = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        if path.name == ALLOWED_STREAMLIT_FILE:
            continue
        if _imports_streamlit(_imported_modules(path)):
            offenders.append(path.name)
    assert not offenders, f"streamlit imported outside ui_streamlit.py: {offenders}"
    # The UI module genuinely imports streamlit.
    assert _imports_streamlit(_imported_modules(UI_MODULE))


def test_core_modules_do_not_import_streamlit():
    for name in CORE_MODULES:
        path = SRC_DIR / name
        assert path.exists(), f"missing core module {name}"
        assert not _imports_streamlit(
            _imported_modules(path)
        ), f"{name} must not import streamlit"


def test_pyproject_adds_only_streamlit_as_new_dependency():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    names = {re.split(r"[<>=!~ ]", d, 1)[0].strip() for d in deps}
    assert "streamlit" in names
    assert names <= ALLOWED_RUNTIME_DEPENDENCIES, (
        f"unexpected runtime dependencies: {names - ALLOWED_RUNTIME_DEPENDENCIES}"
    )
    assert not (names & FORBIDDEN_DEPENDENCIES)


def test_ui_formatters_has_no_streamlit_imports_or_type_references():
    source = UI_FORMATTERS.read_text(encoding="utf-8")
    # No imports, hooks, type hints, or any textual reference at all.
    assert "streamlit" not in source.lower()
    assert not _imports_streamlit(_imported_modules(UI_FORMATTERS))
    # And it can be imported without pulling in streamlit.
    import noxus.ui_formatters  # noqa: F401
    import sys

    assert "streamlit" not in sys.modules
