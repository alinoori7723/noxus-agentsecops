import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", ROOT / "SECURITY.md", *sorted((ROOT / "docs").glob("*.md"))]


def test_local_documentation_links_resolve():
    for document in DOCS:
        for target in re.findall(
            r"(?<!!)\[[^\]]+\]\(([^)]+)\)", document.read_text(encoding="utf-8")
        ):
            if "://" not in target and not target.startswith("#"):
                assert (document.parent / target.split("#", 1)[0]).exists(), (document, target)


def test_readme_identifies_product_and_deployment_boundary():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for phrase in (
        "React",
        "FastAPI",
        "8787",
        "pre-production",
        "no built-in authentication or TLS",
        "not a runtime firewall",
    ):
        assert phrase in readme


def test_security_reporting_is_private():
    policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "/security/advisories/new" in policy
    assert "Earlier releases and archival branches are unsupported" in policy
    assert "Never post real API keys" in policy


def test_current_docs_do_not_link_archived_material():
    for document in DOCS:
        assert "docs/archive/" not in document.read_text(encoding="utf-8")
