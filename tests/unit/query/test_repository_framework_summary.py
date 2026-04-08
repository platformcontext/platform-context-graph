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
                "frameworks": ["nextjs", "react"],
                "react_boundary": "client",
                "react_component_exports": ["default"],
                "react_hooks_used": ["useState"],
                "next_module_kind": "page",
                "next_route_verbs": [],
                "next_metadata_exports": "dynamic",
                "next_route_segments": ["orders"],
                "next_runtime_boundary": "client",
                "next_request_response_apis": [],
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
            },
            {
                "relative_path": "app/api/orders/route.ts",
                "frameworks": ["nextjs"],
                "react_boundary": None,
                "react_component_exports": [],
                "react_hooks_used": [],
                "next_module_kind": "route",
                "next_route_verbs": ["POST", "GET"],
                "next_metadata_exports": "none",
                "next_route_segments": ["api", "orders"],
                "next_runtime_boundary": "server",
                "next_request_response_apis": ["NextResponse"],
            },
        ]
    )

    assert summary == {
        "frameworks": ["nextjs", "react"],
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
                    "relative_path": "app/api/orders/route.ts",
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
                "frameworks": ["nextjs", "react"],
                "react_boundary": "client",
                "react_component_exports": ["default"],
                "react_hooks_used": [],
                "next_module_kind": "page",
                "next_route_verbs": [],
                "next_metadata_exports": "none",
                "next_route_segments": [],
                "next_runtime_boundary": "client",
                "next_request_response_apis": [],
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
    assert params["repo_id"] == "repository:r_demo"
