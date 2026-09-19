import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_tracked_runtime_or_secret_artifacts():
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    forbidden = re.compile(
        r"(^|/)(\.venv[^/]*|node_modules|dist|coverage|\.env|\.claude|__pycache__)(/|$)"
    )
    assert not [name for name in tracked if forbidden.search(name)]


def test_docker_context_excludes_host_dependencies_and_secrets():
    entries = set((ROOT / ".dockerignore").read_text().splitlines())
    assert {".git/", ".venv/", "**/node_modules/", ".env", ".env.*", "reports/"} <= entries
