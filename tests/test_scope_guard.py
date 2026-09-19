import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src" / "noxus"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


FORBIDDEN_MODULES = {
    "vertexai",
    "google.cloud",
    "langgraph",
    "streamlit",
    "requests",
    "httpx",
    "openai",
    "anthropic",
    "google.generativeai",
    "google.genai",
    "boto3",
}


def _imported_modules(source: str) -> set[str]:

    modules: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def _is_forbidden(module: str) -> str | None:

    for forbidden in FORBIDDEN_MODULES:
        if module == forbidden or module.startswith(forbidden + "."):
            return forbidden
    return None


def test_no_out_of_scope_code_present():

    py_files = sorted(SRC_DIR.rglob("*.py"))
    assert py_files, "Expected to find implementation source files to scan."

    violations: list[str] = []
    for path in py_files:
        for module in _imported_modules(path.read_text(encoding="utf-8")):
            forbidden = _is_forbidden(module)
            if forbidden:
                violations.append(f"{path.name}: import '{module}' -> {forbidden}")

    assert not violations, f"Out-of-scope imports detected: {violations}"

    pyproject_text = PYPROJECT.read_text(encoding="utf-8")
    pyproject_allowed = {"httpx"}
    dep_violations = [
        name for name in FORBIDDEN_MODULES - pyproject_allowed if name in pyproject_text
    ]
    assert not dep_violations, (
        f"Out-of-scope dependencies declared in pyproject.toml: {dep_violations}"
    )
