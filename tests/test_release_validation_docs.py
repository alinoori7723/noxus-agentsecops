"""Static checks for the canonical release-validation docs/script, safe Docker
smoke port handling, and the legacy score-field presentation-alias note.

These read files only (no network, no docker, no venv)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = PROJECT_ROOT / "docs" / "submission-checklist.md"
SCRIPT = PROJECT_ROOT / "scripts" / "final_release_validate.sh"

SMOKE_CONTAINER = "noxus-edge-smoke"


def _checklist() -> str:
    return CHECKLIST.read_text(encoding="utf-8")


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Fix 2 — canonical validation environment clarity
# --------------------------------------------------------------------------- #
def test_docs_name_clean_venv_dev_extras_as_canonical_validation():
    text = _checklist().lower()
    assert "canonical release validation" in text
    assert "clean virtual environment" in text
    assert ".[dev]" in _checklist()  # exact extras spec (case-sensitive)


def test_docs_do_not_use_host_pytest_count_as_release_count():
    text = _checklist().lower()
    assert "host" in text
    # Host pytest is explicitly NOT the canonical release count.
    assert "not the canonical release count" in text


def test_final_release_validate_script_exists_and_uses_dev_extras():
    assert SCRIPT.exists(), "scripts/final_release_validate.sh must exist"
    script = _script()
    assert 'install -e ".[dev]"' in script
    # Must not require provider credentials / write secrets.
    lowered = script.lower()
    assert "api_key" not in lowered
    assert "api-key" not in lowered


# --------------------------------------------------------------------------- #
# Fix 4 — safe Docker smoke port handling
# --------------------------------------------------------------------------- #
def test_final_release_validate_uses_named_smoke_container():
    script = _script()
    assert SMOKE_CONTAINER in script
    assert "--name" in script
    # The container is run under the dedicated smoke name.
    assert '--name "$SMOKE_CONTAINER"' in script or f'--name {SMOKE_CONTAINER}' in script


def test_final_release_validate_does_not_stop_unknown_demo_container():
    script = _script()
    stop_lines = [ln for ln in script.splitlines() if "docker stop" in ln]
    assert stop_lines, "script should stop its own smoke container on cleanup"
    for line in stop_lines:
        assert (SMOKE_CONTAINER in line) or ('"$SMOKE_CONTAINER"' in line), (
            f"docker stop must target only the smoke container: {line!r}"
        )
    # Never blanket-stops by published port or arbitrary names.
    assert "docker stop noxus-google-demo" not in script
    assert "docker ps -q" not in script


def test_docs_explain_alternate_smoke_port_when_8787_busy():
    text = _checklist()
    assert "8787" in text
    assert "8877" in text
    low = text.lower()
    assert "busy" in low or "occupied" in low or "fall" in low


# --------------------------------------------------------------------------- #
# Fix 5 — legacy score field presentation-alias documentation
# --------------------------------------------------------------------------- #
def test_docs_document_legacy_score_field_presentation_aliases():
    text = _checklist()
    assert "before_score" in text and "after_score" in text
    assert "legacy" in text.lower()
    assert "Baseline readiness score" in text
    assert "Readiness gate score" in text
    # Explicit guidance not to call these higher-is-better scores "risk score".
    assert "risk score" in text.lower()  # appears only in the "do not label as" guidance
