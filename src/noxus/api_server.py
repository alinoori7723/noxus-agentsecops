"""FastAPI adapter exposing the Noxus orchestrator to the React frontend.

This is a THIN wrapper: all logic lives in the framework-free ``api_core``. The
server maps ``ApiError`` to clean HTTP responses, logs only redacted request
metadata (never the API key), and optionally serves the built React SPA.

Security posture:
- CORS is OFF by default. It is enabled only for local development by setting
  ``NOXUS_ENABLE_DEV_CORS=true`` (origins from ``NOXUS_DEV_CORS_ORIGINS``); it is
  never a wildcard.
- The SPA fallback is confined to the built static directory via a strict
  containment check (no path traversal, no backend source / pyproject leakage).
- The opt-in audit export writes only under the configured audit directory.

Run locally:
    uvicorn noxus.api_server:app --port 8787
or:
    python -m noxus.api_server            # honors NOXUS_API_PORT (default 8787)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import api_core

logger = logging.getLogger("noxus.api")

DEFAULT_DEV_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _test_count() -> Optional[int]:
    raw = os.environ.get("NOXUS_TEST_COUNT")
    if raw and raw.isdigit():
        return int(raw)
    return None


def _resolve_static_dir() -> Optional[Path]:
    """Locate the built React app (Vite ``dist``), if present."""
    candidates = []
    env_dir = os.environ.get("NOXUS_WEB_DIST")
    if env_dir:
        candidates.append(Path(env_dir))
    pkg_dir = Path(__file__).resolve().parent
    candidates.append(pkg_dir / "web_static")  # baked into the container image
    repo_root = pkg_dir.parents[1]
    candidates.append(repo_root / "apps" / "web" / "dist")  # local dev build
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "index.html").exists():
            return candidate.resolve()
    return None


def _dev_cors_enabled() -> bool:
    return os.environ.get("NOXUS_ENABLE_DEV_CORS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _dev_cors_origins() -> list[str]:
    raw = os.environ.get("NOXUS_DEV_CORS_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or list(DEFAULT_DEV_CORS_ORIGINS)


def create_app() -> FastAPI:
    """Build the FastAPI app. Reads env at call time so config is testable."""
    app = FastAPI(title=api_core.PRODUCT_NAME, version="0.1.0")

    # CORS is OFF by default. Only enabled, with an explicit non-wildcard origin
    # allowlist, for LOCAL development when NOXUS_ENABLE_DEV_CORS is truthy.
    if _dev_cors_enabled():
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_dev_cors_origins(),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

    # ----------------------------------------------------------------------- #
    # API routes
    # ----------------------------------------------------------------------- #
    @app.get("/api/health")
    def health() -> dict:
        return api_core.health_payload()

    @app.get("/api/sample-inputs")
    def sample_inputs() -> dict:
        return api_core.sample_inputs()

    @app.get("/api/proof")
    def proof() -> dict:
        return api_core.proof_indicators(test_count=_test_count())

    @app.post("/api/assessments/run")
    def run_assessment(req: api_core.RunAssessmentRequest) -> dict:
        # Log only redacted metadata — never the provider api_key.
        logger.info("run_assessment request: %s", api_core.redact_request(req))
        try:
            _report, response = api_core.run_assessment(req)
        except api_core.ApiError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        return response

    @app.post("/api/providers/test")
    def test_provider(req: api_core.ProviderTestRequest) -> dict:
        # Log only the provider type + roles — never the api_key or provider_config.
        logger.info(
            "provider test: type=%s roles=%s",
            req.provider_config.provider_type,
            req.models_to_test,
        )
        try:
            return api_core.test_provider(req.provider_config, req.models_to_test)
        except api_core.ApiError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    @app.post("/api/audit/export-local")
    def export_audit(req: api_core.AuditExportRequest) -> dict:
        # Writes ONLY under the server-configured audit dir; client supplies at
        # most a sanitized filename, never a path.
        try:
            path = api_core.export_audit_local(req.report, req.filename)
        except api_core.ApiError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        return {"ok": True, "path": path}

    # ----------------------------------------------------------------------- #
    # Static SPA serving (only when a built frontend is present)
    # ----------------------------------------------------------------------- #
    static_dir = _resolve_static_dir()

    if static_dir is not None:
        index_file = static_dir / "index.html"
        assets = static_dir / "assets"
        if assets.is_dir():
            # StaticFiles is itself traversal-safe; it serves hashed bundles.
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(str(index_file))

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str):
            # The /api namespace is handled above; never fall back for it.
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            safe = api_core.resolve_safe_static_path(static_dir, full_path)
            if safe is None:
                # Absolute path / traversal / escapes the static root.
                raise HTTPException(status_code=404, detail="Not found")
            if safe.is_file():
                return FileResponse(str(safe))
            # Safe but not an existing file -> SPA client route -> index.html.
            return FileResponse(str(index_file))
    else:

        @app.get("/")
        def root_no_ui() -> JSONResponse:
            return JSONResponse(
                {
                    "product": api_core.PRODUCT_NAME,
                    "ui": "not built",
                    "hint": "Build apps/web (npm run build) or set NOXUS_WEB_DIST. "
                    "API is available under /api/.",
                }
            )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    port = int(os.environ.get("NOXUS_API_PORT", "8787"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
