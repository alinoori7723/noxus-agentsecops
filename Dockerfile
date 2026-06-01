# Noxus AgentSecOps — production image (React frontend + FastAPI backend).
# Boring on purpose: deterministic core + agent layer + React/Tailwind cockpit
# served by a minimal FastAPI/uvicorn API. No cloud CLIs, no provider SDKs, no
# runtime gateway.

# ---------------------------------------------------------------------------- #
# Stage 1 — build the React frontend (Vite -> static dist).
# ---------------------------------------------------------------------------- #
FROM node:20-slim AS web-build

WORKDIR /web

# Install deps reproducibly from the committed lockfile so the Docker build
# matches the reviewed lockfile and cannot drift.
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund

# Build the static SPA.
COPY apps/web/ ./
RUN npm run build

# ---------------------------------------------------------------------------- #
# Stage 2 — Python backend + bundled static frontend.
# ---------------------------------------------------------------------------- #
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NOXUS_API_PORT=8787 \
    NOXUS_WEB_DIST=/app/web_static \
    NOXUS_TEST_COUNT=152

# Non-root runtime user.
RUN useradd --create-home --uid 1000 noxus_user

WORKDIR /app

# Install the backend package (pulls pydantic, PyYAML, fastapi, uvicorn).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Copy the built frontend from the web-build stage into the served static dir.
COPY --from=web-build /web/dist /app/web_static

# Drop privileges.
RUN chown -R noxus_user:noxus_user /app
USER noxus_user

EXPOSE 8787

# Default: start the FastAPI server, which serves the React SPA and the /api
# routes on NOXUS_API_PORT (default 8787). JSON exec form (with sh -c) avoids the
# JSONArgsRecommended warning while still expanding the env var at runtime.
# The deterministic CLI can still be run by overriding the command, e.g.:
#   docker run --rm noxus-agentsecops:react-local noxus run --mode deterministic ...
CMD ["sh", "-c", "exec uvicorn noxus.api_server:app --host 0.0.0.0 --port ${NOXUS_API_PORT:-8787}"]
