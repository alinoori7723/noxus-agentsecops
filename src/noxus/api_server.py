from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import api_core
from .provider_profiles import profile_catalog, resolve_provider_selection

logger = logging.getLogger("noxus.api")

DEFAULT_DEV_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _http_error(exc: api_core.ApiError) -> HTTPException:

    if exc.code:
        detail = {"message": exc.message, "code": exc.code, **(exc.details or {})}
        return HTTPException(status_code=exc.status_code, detail=detail)
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _test_count() -> int | None:
    raw = os.environ.get("NOXUS_TEST_COUNT")
    if raw and raw.isdigit():
        return int(raw)
    return None


def _resolve_static_dir() -> Path | None:

    candidates = []
    env_dir = os.environ.get("NOXUS_WEB_DIST")
    if env_dir:
        candidates.append(Path(env_dir))
    pkg_dir = Path(__file__).resolve().parent
    candidates.append(pkg_dir / "web_static")
    repo_root = pkg_dir.parents[1]
    candidates.append(repo_root / "apps" / "web" / "dist")
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

    app = FastAPI(title=api_core.PRODUCT_NAME, version="0.1.0")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": {"code": "invalid_request", "message": "Request validation failed."}
            },
        )

    if _dev_cors_enabled():
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_dev_cors_origins(),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

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
    def run_assessment(req: api_core.RunAssessmentRequest, request: Request) -> dict:
        try:
            if (
                req.mode == "agent_assisted"
                or req.provider_config is not None
                or req.provider_profile is not None
            ):
                config = resolve_provider_selection(
                    req.provider_profile,
                    req.provider_config,
                    client_host=request.client.host if request.client else None,
                )
                req = req.model_copy(update={"provider_config": config})
            logger.info(
                "run_assessment mode=%s",
                req.mode if req.mode in ("deterministic", "agent_assisted") else "invalid",
            )
            _report, response = api_core.run_assessment(req)
        except api_core.ApiError as exc:
            raise _http_error(exc) from exc
        return response

    @app.get("/api/providers")
    def providers(request: Request) -> dict:
        try:
            return profile_catalog(client_host=request.client.host if request.client else None)
        except api_core.ApiError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/providers/test")
    def test_provider(req: api_core.ProviderTestRequest, request: Request) -> dict:
        try:
            config = resolve_provider_selection(
                req.provider_profile,
                req.provider_config,
                client_host=request.client.host if request.client else None,
            )
            return api_core.test_provider(config, req.models_to_test)
        except api_core.ApiError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/audit/export-local")
    def export_audit(req: api_core.AuditExportRequest) -> dict:

        try:
            path = api_core.export_audit_local(req.report, req.filename)
        except api_core.ApiError as exc:
            raise _http_error(exc) from exc
        return {"ok": True, "path": path}

    static_dir = _resolve_static_dir()

    if static_dir is not None:
        index_file = static_dir / "index.html"
        assets = static_dir / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(str(index_file))

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str):

            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")

            safe = api_core.resolve_safe_static_path(static_dir, full_path)
            if safe is not None and safe.is_file():
                return FileResponse(str(safe))

            if api_core.is_frontend_route(full_path):
                return FileResponse(str(index_file))
            raise HTTPException(status_code=404, detail="Not found")
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
    uvicorn.run(
        app, host=os.environ.get("NOXUS_API_HOST", "127.0.0.1"), port=port, proxy_headers=False
    )


if __name__ == "__main__":
    main()
