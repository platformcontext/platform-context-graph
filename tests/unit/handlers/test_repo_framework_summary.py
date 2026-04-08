"""Tests for framework-aware repository summary wiring."""

from __future__ import annotations

from unittest.mock import patch

from platform_context_graph.mcp.tools.handlers.ecosystem import get_repo_summary


def test_get_repo_summary_includes_framework_summary_and_story_line() -> None:
    """Repository summaries should surface framework-aware graph evidence."""

    context = {
        "repository": {
            "id": "repository:r_demo",
            "name": "portal-app",
            "discovered_file_count": 12,
            "file_count": 12,
            "files_by_extension": {"tsx": 6},
        },
        "code": {"functions": 4, "classes": 1},
        "infrastructure": {},
        "ecosystem": {"dependencies": [], "dependents": []},
        "coverage": None,
        "platforms": [],
        "deploys_from": [],
        "discovers_config_in": [],
        "provisioned_by": [],
        "provisions_dependencies_for": [],
        "environments": [],
        "observed_config_environments": [],
        "delivery_workflows": {},
        "delivery_paths": [],
        "controller_driven_paths": [],
        "deployment_artifacts": {},
        "consumer_repositories": [],
        "api_surface": {},
        "hostnames": [],
        "limitations": [],
        "framework_summary": {
            "frameworks": ["nextjs", "react"],
            "nextjs": {
                "module_count": 2,
                "page_count": 1,
                "layout_count": 1,
                "route_count": 0,
                "metadata_module_count": 1,
                "route_handler_module_count": 0,
                "client_runtime_count": 1,
                "server_runtime_count": 1,
                "route_verbs": [],
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
        },
    }

    with patch(
        "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
        return_value=context,
    ):
        result = get_repo_summary(object(), "portal-app")

    assert result["framework_summary"]["nextjs"]["page_count"] == 1
    assert any("Framework evidence shows" in line for line in result["story"])
