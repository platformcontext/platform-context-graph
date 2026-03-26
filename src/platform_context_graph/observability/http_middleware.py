"""HTTP middleware helpers for observability runtime wiring."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .otel import FastAPI, new_request_id
from .structured_logging import emit_structured_log

if TYPE_CHECKING:
    from .runtime import ObservabilityRuntime


def install_http_middleware(app: FastAPI, runtime: ObservabilityRuntime) -> None:
    """Install HTTP request metrics and structured request logging once."""

    if getattr(app.state, "_pcg_http_metrics_installed", False):
        return

    @app.middleware("http")
    async def _pcg_http_metrics(request: Any, call_next: Callable[..., Any]) -> Any:
        path = request.url.path
        if path in runtime.excluded_urls:
            return await call_next(request)

        start = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        correlation_id = request.headers.get("X-Correlation-ID") or request_id
        route = path
        with runtime.request_context(
            component="api",
            transport="http",
            request_id=request_id,
            correlation_id=correlation_id,
        ):
            try:
                response = await call_next(request)
                status_code = response.status_code
                route = getattr(request.scope.get("route"), "path", path)
                response.headers["X-Request-ID"] = request_id
                runtime.record_http_request(
                    method=request.method,
                    route=route,
                    status_code=status_code,
                    duration_seconds=time.perf_counter() - start,
                )
                emit_structured_log(
                    logging.getLogger(__name__),
                    logging.INFO,
                    f"HTTP request completed for {request.method} {route}",
                    event_name="http.request.completed",
                    extra_keys={
                        "http_method": request.method,
                        "http_path": path,
                        "http_route": route,
                        "http_status_code": status_code,
                        "duration_seconds": round(time.perf_counter() - start, 6),
                    },
                )
            except Exception:
                status_code = 500
                route = getattr(request.scope.get("route"), "path", path)
                runtime.record_http_request(
                    method=request.method,
                    route=route,
                    status_code=status_code,
                    duration_seconds=time.perf_counter() - start,
                )
                emit_structured_log(
                    logging.getLogger(__name__),
                    logging.ERROR,
                    f"HTTP request failed for {request.method} {route}",
                    event_name="http.request.failed",
                    extra_keys={
                        "http_method": request.method,
                        "http_path": path,
                        "http_route": route,
                        "http_status_code": status_code,
                        "duration_seconds": round(time.perf_counter() - start, 6),
                    },
                    exc_info=True,
                )
                raise

        return response

    app.state._pcg_http_metrics_installed = True
