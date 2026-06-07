#!/usr/bin/env bash
#
# Canonical release validation for Noxus AgentSecOps.
#
# This is the AUTHORITATIVE release-validation entry point. It uses a CLEAN
# virtual environment with the dev extras (`pip install -e '.[dev]'`) so the
# Python test count is reproducible and does not depend on whatever happens to be
# installed on the host. (Host `pytest` is a fast local check only — it can
# report FEWER tests when optional dev extras such as httpx are missing, so it is
# never the canonical release count.)
#
# It requires NO provider credentials and never writes secrets. All temporary
# artifacts (venv / node_modules / dist) are removed at the end.
#
# Docker smoke uses a DEDICATED, named smoke container on a fallback port so it
# never disturbs an existing demo container:
#   - default demo port: 8787
#   - smoke fallback port (used when 8787 is busy): 8877
# The script only ever stops the smoke container it started itself; it never
# stops an unknown/arbitrary demo container.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_DIR=".venv-release-validate"
SMOKE_CONTAINER="noxus-edge-smoke"
SMOKE_IMAGE="noxus-agentsecops:release-validate"
DEFAULT_PORT=8787
FALLBACK_PORT=8877

cleanup() {
  # Only ever stop the smoke container THIS script started.
  docker stop "$SMOKE_CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$VENV_DIR" apps/web/node_modules apps/web/dist
}
trap cleanup EXIT

echo "== 1. Clean venv + dev extras (canonical) =="
rm -rf "$VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -e ".[dev]"
"$VENV_DIR/bin/pytest" -q

echo "== 2. Frontend build + test =="
( cd apps/web && npm ci && npm run build && npm run test )

echo "== 3. Docker build =="
docker build -t "$SMOKE_IMAGE" .

echo "== 4. Docker/API smoke (named container, safe port) =="
# Pick a free port: prefer 8787; if it is busy, fall back to 8877. We never stop
# whatever is already on 8787.
PORT="$DEFAULT_PORT"
if docker ps --format '{{.Ports}}' | grep -q "0.0.0.0:${DEFAULT_PORT}->"; then
  PORT="$FALLBACK_PORT"
  echo "Port ${DEFAULT_PORT} is busy; using fallback smoke port ${PORT}."
fi

docker stop "$SMOKE_CONTAINER" >/dev/null 2>&1 || true
docker run -d --rm --name "$SMOKE_CONTAINER" -p "${PORT}:8787" "$SMOKE_IMAGE"
sleep 4

echo "-- /api/health --"
curl -sS "http://127.0.0.1:${PORT}/api/health"; echo
echo "-- /api/proof --"
curl -sS "http://127.0.0.1:${PORT}/api/proof"; echo

echo "-- traversal 404 checks --"
for path in /etc/passwd /../pyproject.toml; do
  code="$(curl --path-as-is -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}${path}")"
  echo "${path} -> ${code}"
  if [ "$code" != "404" ]; then
    echo "SECURITY BLOCKER: ${path} did not return 404 (got ${code})." >&2
    exit 1
  fi
done

echo "== Release validation complete (cleanup runs on exit) =="
