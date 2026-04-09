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
                "module_count": 2,
                "services": ["s3", "ssm"],
                "client_symbols": ["S3Client", "SSMClient"],
                "sample_modules": [],
            },
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
            "fastapi": {
                "module_count": 1,
                "route_path_count": 2,
                "route_methods": ["GET", "POST"],
                "sample_modules": [],
            },
            "flask": {
                "module_count": 1,
                "route_path_count": 1,
                "route_methods": ["GET"],
                "sample_modules": [],
            },
            "gcp": {
                "module_count": 1,
                "services": ["vision"],
                "client_symbols": ["ImageAnnotatorClient"],
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
        == "Framework and provider evidence shows Express has 2 route modules spanning 3 paths with verbs GET, POST and Hapi has 1 route module spanning 2 paths with verbs GET, DELETE and FastAPI has 1 route module spanning 2 paths with verbs GET, POST and Flask has 1 route module spanning 1 path with verbs GET and AWS SDK usage spans 2 modules across services s3, ssm with clients S3Client, SSMClient and GCP SDK usage spans 1 module across services vision with clients ImageAnnotatorClient and Next.js has 1 page module, 1 layout module, 1 route module, 1 metadata provider with verbs GET, POST and React has 1 client module, 1 shared module, 2 component modules, 1 hook-heavy module."
    )


def test_build_framework_story_items_merges_sample_modules() -> None:
    """Framework story items should include sample modules from both packs."""

    items = build_framework_story_items(
        {
            "frameworks": [
                "aws",
                "express",
                "fastapi",
                "flask",
                "gcp",
                "nextjs",
                "react",
            ],
            "aws": {
                "module_count": 1,
                "sample_modules": [{"relative_path": "lib/s3.js"}],
            },
            "express": {
                "module_count": 1,
                "sample_modules": [{"relative_path": "server/routes.js"}],
            },
            "fastapi": {
                "module_count": 1,
                "sample_modules": [{"relative_path": "app/api.py"}],
            },
            "flask": {
                "module_count": 1,
                "sample_modules": [{"relative_path": "proxy.py"}],
            },
            "gcp": {
                "module_count": 1,
                "sample_modules": [{"relative_path": "services/vision.js"}],
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
        {"framework": "aws", "relative_path": "lib/s3.js"},
        {"framework": "gcp", "relative_path": "services/vision.js"},
        {"framework": "express", "relative_path": "server/routes.js"},
        {"framework": "fastapi", "relative_path": "app/api.py"},
        {"framework": "flask", "relative_path": "proxy.py"},
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
                "frameworks": [
                    "aws",
                    "express",
                    "fastapi",
                    "flask",
                    "gcp",
                    "nextjs",
                    "react",
                ],
                "aws": {
                    "module_count": 1,
                    "services": ["s3"],
                    "client_symbols": ["S3Client"],
                    "sample_modules": [{"relative_path": "lib/s3.js"}],
                },
                "express": {
                    "module_count": 1,
                    "route_path_count": 1,
                    "route_methods": ["GET"],
                    "sample_modules": [{"relative_path": "server/routes.js"}],
                },
                "fastapi": {
                    "module_count": 1,
                    "route_path_count": 2,
                    "route_methods": ["GET", "POST"],
                    "sample_modules": [{"relative_path": "app/api.py"}],
                },
                "flask": {
                    "module_count": 1,
                    "route_path_count": 1,
                    "route_methods": ["GET"],
                    "sample_modules": [{"relative_path": "proxy.py"}],
                },
                "gcp": {
                    "module_count": 1,
                    "services": ["vision"],
                    "client_symbols": ["ImageAnnotatorClient"],
                    "sample_modules": [{"relative_path": "services/vision.js"}],
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
    assert "Framework and provider evidence shows" in framework_section["summary"]
    assert framework_section["items"] == [
        {"framework": "aws", "relative_path": "lib/s3.js"},
        {"framework": "gcp", "relative_path": "services/vision.js"},
        {"framework": "express", "relative_path": "server/routes.js"},
        {"framework": "fastapi", "relative_path": "app/api.py"},
        {"framework": "flask", "relative_path": "proxy.py"},
        {"framework": "nextjs", "relative_path": "app/page.tsx"},
        {"framework": "react", "relative_path": "app/page.tsx"},
    ]
    assert any(
        "Framework and provider evidence shows" in line for line in result["story"]
    )
