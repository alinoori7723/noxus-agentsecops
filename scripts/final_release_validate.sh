#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
uv sync --frozen --extra dev
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev ruff format --check .
uv run --frozen --extra dev mypy
uv run --frozen --extra dev pytest --cov=noxus --cov-report=term --cov-report=xml
uv run --frozen --extra dev python -m build --wheel --no-isolation
npm ci --prefix apps/web
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
npm run test:coverage --prefix apps/web
npm run build --prefix apps/web
npm audit --prefix apps/web
npm audit --prefix apps/web --omit=dev
mkdir -p reports
uv export --frozen --extra dev --no-emit-project --format requirements-txt --output-file reports/python-audit-requirements.txt
uv run --frozen --extra dev pip-audit --require-hashes --disable-pip -r reports/python-audit-requirements.txt
docker build -t noxus:release-validate .
uv run --frozen --extra dev python scripts/container_smoke.py noxus:release-validate
