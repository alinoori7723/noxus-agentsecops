"""Static doc-hygiene tests: keep release/submission docs in sync with the
React/FastAPI architecture (no stale Streamlit / port 8501 / old test counts)."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
README = PROJECT_ROOT / "README.md"
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
DOCS_DIR = PROJECT_ROOT / "docs"

DOC_FILES = [README] + sorted(DOCS_DIR.glob("*.md"))


def _declared_test_count() -> int:
    """The single source of truth for the proof-chip test count (Dockerfile env)."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    m = re.search(r"NOXUS_TEST_COUNT=(\d+)", text)
    assert m, "Dockerfile must declare NOXUS_TEST_COUNT"
    return int(m.group(1))


def test_docs_do_not_reference_streamlit_or_8501():
    for path in DOC_FILES:
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        assert "8501" not in text, f"{path.name} still references port 8501"
        assert "ui_streamlit" not in lower, f"{path.name} references ui_streamlit"
        assert "streamlit run" not in lower, f"{path.name} has a streamlit run cmd"
        # The only tolerated mention of Streamlit is an explicit removal note.
        for line in lower.splitlines():
            if "streamlit" in line:
                assert "removed" in line, (
                    f"{path.name} still references Streamlit: {line!r}"
                )


def test_docs_reference_react_fastapi_and_8787():
    readme = README.read_text(encoding="utf-8")
    for token in ("React", "FastAPI", "8787"):
        assert token in readme, f"README missing {token!r}"
    # The submission/demo docs should point at the new port.
    for name in ("submission-checklist.md", "demo-script.md"):
        text = (DOCS_DIR / name).read_text(encoding="utf-8")
        assert "8787" in text, f"{name} should reference port 8787"


def test_docs_reference_core_api_endpoints():
    readme = README.read_text(encoding="utf-8")
    for endpoint in (
        "/api/health",
        "/api/proof",
        "/api/sample-inputs",
        "/api/assessments/run",
    ):
        assert endpoint in readme, f"README missing endpoint {endpoint}"


def test_docs_test_count_matches_declared_count():
    count = _declared_test_count()
    readme = README.read_text(encoding="utf-8")
    # Release-verification wording (single declared count, not "live test count").
    assert f"{count} Python tests" in readme, (
        f"README test-count claim must match NOXUS_TEST_COUNT={count}"
    )
    # Stale counts must not be claimed anywhere in the docs.
    stale = (
        "89 passing", "89 automated", "114 passing", "114 automated", "89 passed",
        "201 passing", "201 automated", "201 passed", "201 Python", "201 tests",
        "27 Vitest", "27 frontend",
    )
    for path in DOC_FILES:
        text = path.read_text(encoding="utf-8")
        for s in stale:
            assert s not in text, f"{path.name} has a stale test-count claim: {s!r}"
