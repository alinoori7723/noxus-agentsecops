from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def main() -> None:
    image = sys.argv[1]
    name = f"noxus-smoke-{uuid.uuid4().hex[:12]}"
    container = docker(
        "run",
        "--detach",
        "--rm",
        "--name",
        name,
        "--read-only",
        "--tmpfs",
        "/tmp",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--publish",
        "127.0.0.1::8787",
        image,
    )
    try:
        port = docker("port", container, "8787/tcp").rsplit(":", 1)[1]
        base = f"http://127.0.0.1:{port}"
        for attempt in range(60):
            try:
                with urllib.request.urlopen(base + "/api/health", timeout=2) as response:
                    assert json.load(response)["ok"] is True
                break
            except OSError:
                if attempt == 59:
                    raise
                time.sleep(1)
        assert docker("exec", container, "id", "-u") != "0"
        with urllib.request.urlopen(base + "/") as response:
            assert '<div id="root">' in response.read().decode()
        with urllib.request.urlopen(base + "/api/sample-inputs") as response:
            samples = json.load(response)
        request = urllib.request.Request(
            base + "/api/assessments/run",
            data=json.dumps({"mode": "deterministic", **samples}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            report = json.load(response)
        assert report["report"]["open_risks"]
        assert report["readiness"]["badge"]["state"] != "PASS"
        assert report["red_blue"]["red"]["before_summary"]["total_probes"] > 0
        for path in ("/../pyproject.toml", "/etc/passwd", "/src/noxus/api_server.py"):
            try:
                urllib.request.urlopen(base + path)
                raise AssertionError(f"Unexpected accessible path: {path}")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404
        request = urllib.request.Request(
            base + "/api/providers/test",
            data=b'{"provider_config":{"api_key":"synthetic-smoke-key"}}',
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request)
            raise AssertionError("Manual credentials were accepted by default")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
            assert b"synthetic-smoke-key" not in exc.read()
        print(
            "Container smoke passed: non-root, SPA, health, deterministic assessment, preserved open risk, traversal rejection, manual-key rejection."
        )
    finally:
        subprocess.run(["docker", "logs", container], check=False)
        subprocess.run(["docker", "stop", container], check=True, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
