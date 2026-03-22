"""FastAPI application factories for the HTTP API and combined service mode."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.responses import Response

from ..observability import initialize_observability
from ..domain.responses import IngesterScanRequestResponse, IngesterStatusResponse
from .dependencies import get_database, get_query_services
from .routers import (
    code_router,
    content_router,
    entities_router,
    environments_router,
    impact_router,
    infra_router,
    paths_router,
    repositories_router,
    services_router,
    traces_router,
    workloads_router,
)

API_TITLE = "PlatformContextGraph HTTP API"
API_FALLBACK_VERSION = "0.0.0 (dev)"
API_V0_PREFIX = "/api/v0"
API_V0_OPENAPI_URL = f"{API_V0_PREFIX}/openapi.json"
API_V0_DOCS_URL = f"{API_V0_PREFIX}/docs"
API_V0_REDOC_URL = f"{API_V0_PREFIX}/redoc"

_WORKLOAD_CONTEXT_EXAMPLE = {
    "workload": {
        "id": "workload:payments-api",
        "type": "workload",
        "kind": "service",
        "name": "payments-api",
    },
    "instance": {
        "id": "workload-instance:payments-api:prod",
        "type": "workload_instance",
        "kind": "service",
        "name": "payments-api",
        "environment": "prod",
        "workload_id": "workload:payments-api",
    },
    "repositories": [
        {
            "id": "repository:r_ab12cd34",
            "type": "repository",
            "name": "payments-api",
            "repo_slug": "platformcontext/payments-api",
            "remote_url": "https://github.com/platformcontext/payments-api",
            "local_path": "/srv/repos/payments-api",
            "has_remote": True,
        }
    ],
    "images": [],
    "instances": [],
    "k8s_resources": [],
    "cloud_resources": [],
    "shared_resources": [],
    "dependencies": [],
    "entrypoints": [],
    "evidence": [],
}
_SERVICE_CONTEXT_EXAMPLE = {
    **_WORKLOAD_CONTEXT_EXAMPLE,
    "requested_as": "service",
}
_RESOLVE_ENTITY_RESPONSE_EXAMPLE = {
    "matches": [
        {
            "ref": _WORKLOAD_CONTEXT_EXAMPLE["workload"],
            "score": 0.98,
        }
    ]
}
_CODE_SEARCH_REQUEST_EXAMPLE = {
    "query": "process_payment",
    "repo_id": "repository:r_ab12cd34",
    "exact": False,
    "limit": 10,
}

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
        return pkg_version("platform-context-graph")
    except PackageNotFoundError:
        return API_FALLBACK_VERSION


def _ensure_examples(schema: dict[str, Any]) -> dict[str, Any]:
    """Attach stable example payloads to the generated OpenAPI schema.

    Args:
        schema: Generated OpenAPI schema.

    Returns:
        The mutated schema with curated request and response examples.
    """
    paths = schema.get("paths", {})

    def response_content(path: str, method: str) -> dict[str, Any]:
        """Return the JSON response content schema for a route/method pair."""
        return paths[path][method]["responses"]["200"]["content"]["application/json"]

    response_content("/api/v0/workloads/{workload_id}/context", "get")["examples"] = {
        "environment_context": {
            "summary": "Environment-scoped workload context",
            "value": _WORKLOAD_CONTEXT_EXAMPLE,
        }
    }
    response_content("/api/v0/services/{workload_id}/context", "get")["examples"] = {
        "service_alias": {
            "summary": "Service alias over the canonical workload model",
            "value": _SERVICE_CONTEXT_EXAMPLE,
        }
    }
    response_content("/api/v0/entities/resolve", "post")["examples"] = {
        "workload_match": {
            "summary": "Resolve a workload by name",
            "value": _RESOLVE_ENTITY_RESPONSE_EXAMPLE,
        }
    }
    paths["/api/v0/code/search"]["post"]["requestBody"]["content"]["application/json"][
        "examples"
    ] = {
        "code_only": {
            "summary": "Code-only search scoped to a canonical repository",
            "value": _CODE_SEARCH_REQUEST_EXAMPLE,
        }
    }
    return schema


def _build_openapi(app: FastAPI) -> dict[str, Any]:
    """Build and cache the OpenAPI schema for the HTTP API.

    Args:
        app: FastAPI application instance.

    Returns:
        The cached or newly generated OpenAPI schema.
    """
    if app.openapi_schema is not None:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        description=app.description,
    )
    app.openapi_schema = _ensure_examples(schema)
    return app.openapi_schema


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

    app = FastAPI(
        title=API_TITLE,
        version=_get_api_version(),
        openapi_url=API_V0_OPENAPI_URL,
        docs_url=API_V0_DOCS_URL,
        redoc_url=API_V0_REDOC_URL,
    )
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
    app.include_router(entities_router, prefix=API_V0_PREFIX)
    app.include_router(workloads_router, prefix=API_V0_PREFIX)
    app.include_router(services_router, prefix=API_V0_PREFIX)
    app.include_router(traces_router, prefix=API_V0_PREFIX)
    app.include_router(paths_router, prefix=API_V0_PREFIX)
    app.include_router(impact_router, prefix=API_V0_PREFIX)
    app.include_router(environments_router, prefix=API_V0_PREFIX)
    app.include_router(code_router, prefix=API_V0_PREFIX)
    app.include_router(content_router, prefix=API_V0_PREFIX)
    app.include_router(infra_router, prefix=API_V0_PREFIX)
    app.include_router(repositories_router, prefix=API_V0_PREFIX)
    app.openapi = lambda: _build_openapi(app)
    return app


def create_service_app(
    *,
    database_dependency: Callable[..., Any] | None = None,
    query_services_dependency: Callable[..., Any] | None = None,
    mcp_server_dependency: Callable[..., Any] | None = None,
) -> FastAPI:
    """Create the combined HTTP API and MCP transport service application.

    Args:
        database_dependency: Overrideable database dependency factory.
        query_services_dependency: Overrideable query services dependency factory.
        mcp_server_dependency: Optional MCP server dependency factory. API-only
            runtimes may provide an MCP server without a mutation-capable code
            watcher.

    Returns:
        A configured FastAPI application with the HTTP API and MCP transport.
    """

    def _get_mcp_server() -> Any:
        """Resolve the configured MCP server dependency when present."""
        if mcp_server_dependency is None:
            return None
        return mcp_server_dependency()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Manage optional MCP runtime lifecycle hooks around the app runtime.

        The `api` runtime role does not provision a mutation-capable code
        watcher, so watcher startup must remain optional even when an MCP server
        instance exists.
        """
        server = _get_mcp_server()
        watcher = getattr(server, "code_watcher", None) if server is not None else None
        if watcher is not None:
            watcher.start()
        try:
            yield
        finally:
            if server is not None:
                server.shutdown()

    app = create_app(
        database_dependency=database_dependency,
        query_services_dependency=query_services_dependency,
    )
    app.router.lifespan_context = lifespan

    @app.get("/health", tags=["system"])
    async def service_health() -> dict[str, str]:
        """Report service-mode health without forcing database query services."""
        return {"status": "ok"}

    @app.post("/mcp/message", tags=["mcp"])
    async def mcp_message(request: Request) -> Response:
        """Handle HTTP-transported JSON-RPC messages for the MCP server.

        Args:
            request: Incoming FastAPI request containing a JSON-RPC payload.

        Returns:
            A JSON or streaming response representing the MCP server reply.
        """
        server = _get_mcp_server()
        if server is None:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "MCP transport is not configured for this service instance."
                },
            )

        try:
            body = await request.json()
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                },
            )

        response, status_code = await server._handle_jsonrpc_request(
            body, transport="jsonrpc-http"
        )
        if response is None:
            return Response(status_code=204)
        return JSONResponse(content=response, status_code=status_code)

    @app.get("/mcp/sse", tags=["mcp"])
    async def mcp_sse() -> StreamingResponse:
        """Expose a simple SSE keepalive transport for MCP-compatible clients."""

        async def event_stream():
            """Yield periodic keepalive events for the SSE transport."""
            while True:
                yield 'data: {"type":"keepalive"}\n\n'
                import asyncio

                await asyncio.sleep(30)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app
