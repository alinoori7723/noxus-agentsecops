FROM node:24-slim AS web-build
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json apps/web/.npmrc ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.10.9 AS uv

FROM python:3.11-alpine AS python-build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --only-group build && \
    uv run --no-sync python -m build --wheel --no-isolation && \
    uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file requirements.txt

FROM python:3.11-alpine
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NOXUS_API_PORT=8787 \
    NOXUS_API_HOST=0.0.0.0 \
    NOXUS_WEB_DIST=/app/web_static \
    NOXUS_AUDIT_DIR=/app/outputs/audit \
    PATH=/app/.venv/bin:$PATH
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY --from=python-build /build/requirements.txt /tmp/requirements.txt
COPY --from=python-build /build/dist/*.whl /tmp/
RUN apk upgrade --no-cache && \
    /usr/local/bin/python -m pip uninstall --yes setuptools pip && \
    uv venv /app/.venv && \
    uv pip sync --python /app/.venv/bin/python --require-hashes /tmp/requirements.txt && \
    uv pip install --python /app/.venv/bin/python --no-deps /tmp/*.whl && \
    rm -f /tmp/requirements.txt /tmp/*.whl /usr/local/bin/uv && \
    adduser --disabled-password --uid 1000 noxus_user && \
    mkdir -p /app/outputs/audit && chown -R noxus_user:noxus_user /app/outputs
COPY --from=web-build /web/dist /app/web_static
USER noxus_user
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ['NOXUS_API_PORT']+'/api/health', timeout=3)"
CMD ["python", "-m", "noxus.api_server"]
