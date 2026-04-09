"""Tests for repository framework-summary helpers."""

from __future__ import annotations

from platform_context_graph.query.repositories.framework_summary import (
    build_repository_framework_summary,
)
from platform_context_graph.query.repositories.framework_summary import (
    summarize_repository_framework_rows,
)


class _Session:
    """Capture one framework-summary query."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, object]]] = []

    def run(self, query: str, **kwargs):
        self.calls.append((query, kwargs))

        class _Result:
            def __init__(self, rows: list[dict[str, object]]) -> None:
                self._rows = rows

            def data(self) -> list[dict[str, object]]:
                return self._rows

        return _Result(self.rows)


def test_summarize_repository_framework_rows_counts_nextjs_and_react() -> None:
    """Framework rows should produce bounded React and Next.js summaries."""

    summary = summarize_repository_framework_rows(
        [
            {
                "relative_path": "app/orders/page.tsx",
                "frameworks": ["aws", "express", "fastapi", "nextjs", "react"],
                "react_boundary": "client",
                "react_component_exports": ["default"],
                "react_hooks_used": ["useState"],
                "next_module_kind": "page",
                "next_route_verbs": [],
                "next_metadata_exports": "dynamic",
                "next_route_segments": ["orders"],
                "next_runtime_boundary": "client",
                "next_request_response_apis": [],
                "express_route_methods": ["GET"],
                "express_route_paths": ["/orders"],
                "express_server_symbols": ["router"],
                "hapi_route_methods": [],
                "hapi_route_paths": [],
                "hapi_server_symbols": [],
                "fastapi_route_methods": ["GET"],
                "fastapi_route_paths": ["/health"],
                "fastapi_server_symbols": ["app"],
                "flask_route_methods": [],
                "flask_route_paths": [],
                "flask_server_symbols": [],
                "aws_services": ["s3"],
                "aws_client_symbols": ["S3Client"],
                "gcp_services": [],
                "gcp_client_symbols": [],
            },
            {
                "relative_path": "app/orders/layout.tsx",
                "frameworks": ["nextjs", "react"],
                "react_boundary": "shared",
                "react_component_exports": ["default"],
                "react_hooks_used": [],
                "next_module_kind": "layout",
                "next_route_verbs": [],
                "next_metadata_exports": "none",
                "next_route_segments": ["orders"],
                "next_runtime_boundary": "server",
                "next_request_response_apis": [],
                "express_route_methods": [],
                "express_route_paths": [],
                "express_server_symbols": [],
                "hapi_route_methods": [],
                "hapi_route_paths": [],
                "hapi_server_symbols": [],
                "fastapi_route_methods": [],
                "fastapi_route_paths": [],
                "fastapi_server_symbols": [],
                "flask_route_methods": [],
                "flask_route_paths": [],
                "flask_server_symbols": [],
                "aws_services": [],
                "aws_client_symbols": [],
                "gcp_services": [],
                "gcp_client_symbols": [],
            },
            {
                "relative_path": "routes/orders.py",
                "frameworks": ["flask", "gcp", "hapi", "nextjs"],
                "react_boundary": None,
                "react_component_exports": [],
                "react_hooks_used": [],
                "next_module_kind": "route",
                "next_route_verbs": ["POST", "GET"],
                "next_metadata_exports": "none",
                "next_route_segments": ["api", "orders"],
                "next_runtime_boundary": "server",
                "next_request_response_apis": ["NextResponse"],
                "express_route_methods": [],
                "express_route_paths": [],
                "express_server_symbols": [],
                "hapi_route_methods": ["POST", "GET"],
                "hapi_route_paths": ["/orders", "/orders/{id}"],
                "hapi_server_symbols": [],
                "fastapi_route_methods": [],
                "fastapi_route_paths": [],
                "fastapi_server_symbols": [],
                "flask_route_methods": ["POST"],
                "flask_route_paths": ["/proxy"],
                "flask_server_symbols": ["app"],
                "aws_services": [],
                "aws_client_symbols": [],
                "gcp_services": ["vision"],
                "gcp_client_symbols": ["ImageAnnotatorClient"],
            },
        ]
    )

    assert summary == {
        "frameworks": [
            "aws",
            "express",
            "fastapi",
            "flask",
            "gcp",
            "hapi",
            "nextjs",
            "react",
        ],
        "aws": {
            "module_count": 1,
            "services": ["s3"],
            "client_symbols": ["S3Client"],
            "sample_modules": [
                {
                    "relative_path": "app/orders/page.tsx",
                    "services": ["s3"],
                    "client_symbols": ["S3Client"],
                }
            ],
        },
        "react": {
            "module_count": 2,
            "client_boundary_count": 1,
            "server_boundary_count": 0,
            "shared_boundary_count": 1,
            "component_module_count": 2,
            "hook_module_count": 1,
            "sample_modules": [
                {
                    "relative_path": "app/orders/page.tsx",
                    "boundary": "client",
                    "component_exports": ["default"],
                    "hooks_used": ["useState"],
                },
                {
                    "relative_path": "app/orders/layout.tsx",
                    "boundary": "shared",
                    "component_exports": ["default"],
                    "hooks_used": [],
                },
            ],
        },
        "express": {
            "module_count": 1,
            "route_path_count": 1,
            "route_methods": ["GET"],
            "sample_modules": [
                {
                    "relative_path": "app/orders/page.tsx",
                    "route_methods": ["GET"],
                    "route_paths": ["/orders"],
                    "server_symbols": ["router"],
                }
            ],
        },
        "fastapi": {
            "module_count": 1,
            "route_path_count": 1,
            "route_methods": ["GET"],
            "sample_modules": [
                {
                    "relative_path": "app/orders/page.tsx",
                    "route_methods": ["GET"],
                    "route_paths": ["/health"],
                    "server_symbols": ["app"],
                }
            ],
        },
        "flask": {
            "module_count": 1,
            "route_path_count": 1,
            "route_methods": ["POST"],
            "sample_modules": [
                {
                    "relative_path": "routes/orders.py",
                    "route_methods": ["POST"],
                    "route_paths": ["/proxy"],
                    "server_symbols": ["app"],
                }
            ],
        },
        "gcp": {
            "module_count": 1,
            "services": ["vision"],
            "client_symbols": ["ImageAnnotatorClient"],
            "sample_modules": [
                {
                    "relative_path": "routes/orders.py",
                    "services": ["vision"],
                    "client_symbols": ["ImageAnnotatorClient"],
                }
            ],
        },
        "hapi": {
            "module_count": 1,
            "route_path_count": 2,
            "route_methods": ["GET", "POST"],
            "sample_modules": [
                {
                    "relative_path": "routes/orders.py",
                    "route_methods": ["GET", "POST"],
                    "route_paths": ["/orders", "/orders/{id}"],
                    "server_symbols": [],
                }
            ],
        },
        "nextjs": {
            "module_count": 3,
            "page_count": 1,
            "layout_count": 1,
            "route_count": 1,
            "metadata_module_count": 1,
            "route_handler_module_count": 1,
            "client_runtime_count": 1,
            "server_runtime_count": 2,
            "route_verbs": ["GET", "POST"],
            "sample_modules": [
                {
                    "relative_path": "app/orders/page.tsx",
                    "module_kind": "page",
                    "route_verbs": [],
                    "metadata_exports": "dynamic",
                    "route_segments": ["orders"],
                    "runtime_boundary": "client",
                },
                {
                    "relative_path": "app/orders/layout.tsx",
                    "module_kind": "layout",
                    "route_verbs": [],
                    "metadata_exports": "none",
                    "route_segments": ["orders"],
                    "runtime_boundary": "server",
                },
                {
                    "relative_path": "routes/orders.py",
                    "module_kind": "route",
                    "route_verbs": ["GET", "POST"],
                    "metadata_exports": "none",
                    "route_segments": ["api", "orders"],
                    "runtime_boundary": "server",
                },
            ],
        },
    }


def test_build_repository_framework_summary_queries_file_properties() -> None:
    """Framework summary should be derived from File-node framework fields."""

    session = _Session(
        [
            {
                "relative_path": "app/page.tsx",
                "frameworks": [
                    "aws",
                    "express",
                    "fastapi",
                    "flask",
                    "gcp",
                    "nextjs",
                    "react",
                ],
                "react_boundary": "client",
                "react_component_exports": ["default"],
                "react_hooks_used": [],
                "next_module_kind": "page",
                "next_route_verbs": [],
                "next_metadata_exports": "none",
                "next_route_segments": [],
                "next_runtime_boundary": "client",
                "next_request_response_apis": [],
                "express_route_methods": ["GET"],
                "express_route_paths": ["/health"],
                "express_server_symbols": ["app"],
                "hapi_route_methods": [],
                "hapi_route_paths": [],
                "hapi_server_symbols": [],
                "fastapi_route_methods": ["POST"],
                "fastapi_route_paths": ["/predict"],
                "fastapi_server_symbols": ["app"],
                "flask_route_methods": ["GET"],
                "flask_route_paths": ["/healthz"],
                "flask_server_symbols": ["app"],
                "aws_services": ["ssm"],
                "aws_client_symbols": ["SSMClient"],
                "gcp_services": ["vision"],
                "gcp_client_symbols": ["ImageAnnotatorClient"],
            }
        ]
    )

    summary = build_repository_framework_summary(
        session,
        {"id": "repository:r_demo", "name": "demo", "path": "/repos/demo"},
    )

    assert summary is not None
    query, params = session.calls[0]
    assert "f.react_boundary as react_boundary" in query
    assert "f.next_module_kind as next_module_kind" in query
    assert "f.express_route_methods as express_route_methods" in query
    assert "f.hapi_route_methods as hapi_route_methods" in query
    assert "f.fastapi_route_methods as fastapi_route_methods" in query
    assert "f.flask_route_methods as flask_route_methods" in query
    assert "f.aws_services as aws_services" in query
    assert "f.gcp_services as gcp_services" in query
    assert params["repo_id"] == "repository:r_demo"
