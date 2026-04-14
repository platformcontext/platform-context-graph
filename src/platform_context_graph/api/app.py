"""FastAPI application factories for the HTTP API and combined service mode."""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version as pkg_version
import os
from pathlib import Path
import tempfile
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse
from starlette.responses import Response

from ..cli.config_manager import get_config_value
from ..core.pcg_bundle import PCGBundle
from ..observability import initialize_observability
from ..versioning import ensure_v_prefix
from ..domain.responses import IngesterScanRequestResponse, IngesterStatusResponse
from .dependencies import get_database, get_query_services
from .http_auth import http_auth_middleware
from .app_openapi import build_openapi_schema
from .routers import (
    admin_router,
)

API_TITLE = "PlatformContextGraph HTTP API"
API_FALLBACK_VERSION = "v0.0.0 (dev)"
API_V0_PREFIX = "/api/v0"
API_V0_OPENAPI_URL = f"{API_V0_PREFIX}/openapi.json"
API_V0_DOCS_URL = f"{API_V0_PREFIX}/docs"
API_V0_REDOC_URL = f"{API_V0_PREFIX}/redoc"
MAX_BUNDLE_UPLOAD_BYTES = int(
    os.getenv("PCG_MAX_BUNDLE_UPLOAD_BYTES", str(64 * 1024 * 1024))
)

__all__ = [
    "API_TITLE",
    "API_V0_DOCS_URL",
    "API_V0_OPENAPI_URL",
    "API_V0_PREFIX",
    "API_V0_REDOC_URL",
    "create_app",
    "create_service_app",
]


def _get_api_version() -> str:
    """Return the installed package version or a development fallback."""
    try:
        return ensure_v_prefix(pkg_version("platform-context-graph"))
    except PackageNotFoundError:
        return API_FALLBACK_VERSION


def _public_docs_enabled() -> bool:
    """Return whether OpenAPI and interactive docs should be exposed."""

    configured = os.getenv("PCG_ENABLE_PUBLIC_DOCS")
    if configured is None:
        configured = get_config_value("PCG_ENABLE_PUBLIC_DOCS")
    if configured is None or not str(configured).strip():
        return True
    return str(configured).strip().lower() == "true"


def _import_uploaded_bundle(
    database: Any,
    bundle_path: Path,
    *,
    clear_existing: bool = False,
) -> dict[str, Any]:
    """Import one uploaded ``.pcg`` bundle into the configured database."""

    bundle = PCGBundle(database)
    success, message = bundle.import_from_bundle(
        bundle_path,
        clear_existing=clear_existing,
    )
    return {
        "success": success,
        "message": message,
    }


def create_app(
    *,
    database_dependency: Callable[..., Any] | None = None,
    query_services_dependency: Callable[..., Any] | None = None,
) -> FastAPI:
    """Create the HTTP API application.

    Args:
        database_dependency: Overrideable database dependency factory.
        query_services_dependency: Overrideable query services dependency factory.

    Returns:
        A configured FastAPI application.
    """

    public_docs_enabled = _public_docs_enabled()
    app = FastAPI(
        title=API_TITLE,
        version=_get_api_version(),
        openapi_url=API_V0_OPENAPI_URL if public_docs_enabled else None,
        docs_url=API_V0_DOCS_URL if public_docs_enabled else None,
        redoc_url=API_V0_REDOC_URL if public_docs_enabled else None,
    )
    app.middleware("http")(http_auth_middleware)
    initialize_observability(component="api", app=app)

    if database_dependency is not None:
        app.dependency_overrides[get_database] = database_dependency
    if query_services_dependency is not None:
        app.dependency_overrides[get_query_services] = query_services_dependency

    if query_services_dependency is not None:
        health_dependency = get_query_services
    elif database_dependency is not None:
        health_dependency = get_database
    else:
        health_dependency = get_query_services

    router = APIRouter(prefix=API_V0_PREFIX)

    @router.get("/health", tags=["system"])
    def health(_services: Any = Depends(health_dependency)) -> dict[str, str]:
        """Report a simple health check for dependency-initialized API mode."""
        return {"status": "ok"}

    @router.get("/index-status", tags=["system"])
    def index_status(
        target: str | None = None,
        services: Any = Depends(get_query_services),
    ) -> dict[str, Any]:
        """Return the latest checkpointed index status for a path or run ID."""
        try:
            from ..query import status as status_queries
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="Index status query has migrated to Go API. Use the Go query endpoints.",
            )

        summary = status_queries.describe_index_status(
            services.database,
            target=target or status_queries.default_index_status_target("repository"),
            ingester="repository",
        )
        if summary is None:
            raise HTTPException(status_code=404, detail="Index status not found")
        return summary

    @router.get("/index-runs/{run_id}/coverage", tags=["system"])
    def index_run_coverage(
        run_id: str,
        only_incomplete: bool = False,
        limit: int = 100,
        services: Any = Depends(get_query_services),
    ) -> dict[str, Any]:
        """Return durable repository coverage rows for one checkpointed run."""

        return services.repositories.list_repository_coverage(
            services.database,
            run_id=run_id,
            only_incomplete=only_incomplete,
            limit=limit,
        )

    @router.get("/index-runs/{run_id}", tags=["system"])
    def index_run_status(
        run_id: str,
        services: Any = Depends(get_query_services),
    ) -> dict[str, Any]:
        """Return the checkpointed status summary for one run identifier."""
        try:
            from ..query import status as status_queries
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="Index status query has migrated to Go API. Use the Go query endpoints.",
            )

        summary = status_queries.describe_index_status(
            services.database,
            target=run_id,
            ingester="repository",
        )
        if summary is None:
            raise HTTPException(status_code=404, detail="Index run not found")
        return summary

    @router.post("/bundles/import", tags=["system"])
    async def import_bundle(
        bundle: UploadFile = File(...),
        clear_existing: bool = Form(False),
        database: Any = Depends(get_database),
    ) -> dict[str, Any]:
        """Import an uploaded ``.pcg`` bundle into the active graph database."""

        temp_path: Path | None = None
        try:
            suffix = Path(bundle.filename or "uploaded-bundle.pcg").suffix or ".pcg"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                temp_path = Path(handle.name)
                bytes_written = 0
                while chunk := await bundle.read(1024 * 1024):
                    bytes_written += len(chunk)
                    if bytes_written > MAX_BUNDLE_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail="Bundle upload exceeds maximum allowed size.",
                        )
                    handle.write(chunk)

            result = _import_uploaded_bundle(
                database,
                temp_path,
                clear_existing=clear_existing,
            )
        finally:
            await bundle.close()
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=str(result.get("message") or "Bundle import failed"),
            )
        return result

    @router.get(
        "/ingesters",
        tags=["system"],
        response_model=list[IngesterStatusResponse],
        response_model_exclude_none=True,
    )
    def list_ingesters(
        services: Any = Depends(get_query_services),
    ) -> list[dict[str, Any]]:
        """Return the latest persisted status for each configured ingester."""

        return services.status.list_ingesters(services.database)

    @router.post(
        "/ingesters/{ingester}/scan",
        tags=["system"],
        response_model=IngesterScanRequestResponse,
        response_model_exclude_none=True,
    )
    def request_ingester_scan(
        ingester: str,
        services: Any = Depends(get_query_services),
    ) -> dict[str, Any]:
        """Persist a manual scan request for one ingester."""

        known_ingesters = getattr(services.status, "KNOWN_INGESTERS", ("repository",))
        if ingester not in known_ingesters:
            raise HTTPException(status_code=404, detail=f"Unknown ingester: {ingester}")

        return services.status.request_ingester_scan_control(
            services.database,
            ingester=ingester,
            requested_by="api",
        )

    @router.get(
        "/ingesters/{ingester}",
        tags=["system"],
        response_model=IngesterStatusResponse,
        response_model_exclude_none=True,
    )
    def get_ingester_status(
        ingester: str,
        services: Any = Depends(get_query_services),
    ) -> dict[str, Any]:
        """Return the latest persisted status for one ingester."""

        known_ingesters = getattr(services.status, "KNOWN_INGESTERS", ("repository",))
        if ingester not in known_ingesters:
            raise HTTPException(status_code=404, detail=f"Unknown ingester: {ingester}")
        return services.status.get_ingester_status(
            services.database,
            ingester=ingester,
        )

    app.include_router(router)
    app.include_router(admin_router, prefix=API_V0_PREFIX)
    app.openapi = lambda: build_openapi_schema(app)
    return app


def create_service_app(
    *,
    database_dependency: Callable[..., Any] | None = None,
    query_services_dependency: Callable[..., Any] | None = None,
) -> FastAPI:
    """Create the HTTP API service application.

    Args:
        database_dependency: Overrideable database dependency factory.
        query_services_dependency: Overrideable query services dependency factory.

    Returns:
        A configured FastAPI application with the HTTP API.
    """

    app = create_app(
        database_dependency=database_dependency,
        query_services_dependency=query_services_dependency,
    )

    @app.get("/health", tags=["system"])
    async def service_health() -> dict[str, str]:
        """Report service-mode health without forcing database query services."""
        return {"status": "ok"}

    return app
