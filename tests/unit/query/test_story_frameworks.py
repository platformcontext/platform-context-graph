"""Tests for framework-aware repository story helpers."""

from __future__ import annotations

from platform_context_graph.query.story_frameworks import (
    build_framework_story_items,
)
from platform_context_graph.query.story_frameworks import (
    summarize_framework_overview,
)
from platform_context_graph.query.story_repository import (
    build_repository_story_response,
)


def test_summarize_framework_overview_builds_short_story_line() -> None:
    """Framework summaries should turn into one human-readable story line."""

    summary = summarize_framework_overview(
        {
            "frameworks": ["express", "hapi", "nextjs", "react"],
            "express": {
                "module_count": 2,
                "route_path_count": 3,
                "route_methods": ["GET", "POST"],
                "sample_modules": [],
            },
            "hapi": {
                "module_count": 1,
                "route_path_count": 2,
                "route_methods": ["GET", "DELETE"],
                "sample_modules": [],
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
                "sample_modules": [],
            },
            "react": {
                "module_count": 2,
                "client_boundary_count": 1,
                "server_boundary_count": 0,
                "shared_boundary_count": 1,
                "component_module_count": 2,
                "hook_module_count": 1,
                "sample_modules": [],
            },
        }
    )

    assert (
        summary
        == "Framework evidence shows Express has 2 route modules spanning 3 paths with verbs GET, POST and Hapi has 1 route module spanning 2 paths with verbs GET, DELETE and Next.js has 1 page module, 1 layout module, 1 route module, 1 metadata provider with verbs GET, POST and React has 1 client module, 1 shared module, 2 component modules, 1 hook-heavy module."
    )


def test_build_framework_story_items_merges_sample_modules() -> None:
    """Framework story items should include sample modules from both packs."""

    items = build_framework_story_items(
        {
            "frameworks": ["express", "nextjs", "react"],
            "express": {
                "module_count": 1,
                "sample_modules": [{"relative_path": "server/routes.js"}],
            },
            "nextjs": {
                "module_count": 1,
                "sample_modules": [{"relative_path": "app/page.tsx"}],
            },
            "react": {
                "module_count": 1,
                "sample_modules": [{"relative_path": "components/Button.tsx"}],
            },
        }
    )

    assert items == [
        {"framework": "express", "relative_path": "server/routes.js"},
        {"framework": "nextjs", "relative_path": "app/page.tsx"},
        {"framework": "react", "relative_path": "components/Button.tsx"},
    ]


def test_build_repository_story_response_adds_framework_section() -> None:
    """Repository stories should surface framework-aware sections when present."""

    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_demo",
                "name": "portal-app",
                "file_count": 10,
                "discovered_file_count": 10,
            },
            "code": {"functions": 4, "classes": 1},
            "framework_summary": {
                "frameworks": ["express", "nextjs", "react"],
                "express": {
                    "module_count": 1,
                    "route_path_count": 1,
                    "route_methods": ["GET"],
                    "sample_modules": [{"relative_path": "server/routes.js"}],
                },
                "nextjs": {
                    "module_count": 1,
                    "page_count": 1,
                    "layout_count": 0,
                    "route_count": 0,
                    "metadata_module_count": 1,
                    "route_handler_module_count": 0,
                    "client_runtime_count": 1,
                    "server_runtime_count": 0,
                    "route_verbs": [],
                    "sample_modules": [{"relative_path": "app/page.tsx"}],
                },
                "react": {
                    "module_count": 1,
                    "client_boundary_count": 1,
                    "server_boundary_count": 0,
                    "shared_boundary_count": 0,
                    "component_module_count": 1,
                    "hook_module_count": 1,
                    "sample_modules": [{"relative_path": "app/page.tsx"}],
                },
            },
        }
    )

    framework_section = next(
        section for section in result["story_sections"] if section["id"] == "frameworks"
    )
    assert "Framework evidence shows" in framework_section["summary"]
    assert framework_section["items"] == [
        {"framework": "express", "relative_path": "server/routes.js"},
        {"framework": "nextjs", "relative_path": "app/page.tsx"},
        {"framework": "react", "relative_path": "app/page.tsx"},
    ]
    assert any("Framework evidence shows" in line for line in result["story"])
