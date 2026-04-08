"""Framework-surfacing coverage for repository context responses."""

from __future__ import annotations

import pytest

from platform_context_graph.query.repositories.context_data import (
    build_repository_context,
)


class _Result:
    """Minimal query result wrapper for repository-context tests."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def data(self) -> list[dict[str, object]]:
        return self._rows


class _Session:
    """Minimal session stub returning empty query results."""

    def run(self, _query: str, **_kwargs: object) -> _Result:
        return _Result([])


def test_build_repository_context_adds_framework_story(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository context should expose a human-readable framework story."""

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.resolve_repository",
        lambda *_args, **_kwargs: {
            "id": "repository:r_demo",
            "name": "demo-next-app",
            "path": "/repos/demo-next-app",
            "local_path": "/repos/demo-next-app",
            "remote_url": "https://github.com/platformcontext/demo-next-app",
            "repo_slug": "platformcontext/demo-next-app",
            "has_remote": True,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.graph_relationship_types",
        lambda *_args, **_kwargs: set(),
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.repository_graph_counts",
        lambda *_args, **_kwargs: {
            "root_file_count": 0,
            "root_directory_count": 0,
            "file_count": 0,
            "top_level_function_count": 0,
            "class_method_count": 0,
            "total_function_count": 0,
            "class_count": 0,
            "module_count": 0,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_infrastructure",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_ecosystem",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.build_relationship_summary",
        lambda *_args, **_kwargs: {
            "coverage": None,
            "limitations": [],
            "platforms": [],
            "deploys_from": [],
            "discovers_config_in": [],
            "provisioned_by": [],
            "provisions_dependencies_for": [],
            "iac_relationships": [],
            "deployment_chain": [],
            "environments": [],
            "summary": {},
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.build_repository_framework_summary",
        lambda *_args, **_kwargs: {
            "frameworks": ["nextjs", "react"],
            "react": {
                "module_count": 1,
                "client_boundary_count": 1,
                "server_boundary_count": 0,
                "shared_boundary_count": 0,
                "component_module_count": 1,
                "hook_module_count": 0,
                "sample_modules": [],
            },
            "nextjs": {
                "module_count": 1,
                "page_count": 1,
                "layout_count": 0,
                "route_count": 0,
                "metadata_module_count": 0,
                "route_handler_module_count": 0,
                "client_runtime_count": 1,
                "server_runtime_count": 0,
                "route_verbs": [],
                "sample_modules": [],
            },
        },
    )

    result = build_repository_context(_Session(), "demo-next-app")

    assert result["framework_summary"]["frameworks"] == ["nextjs", "react"]
    assert result["framework_story"].startswith("Framework evidence shows ")
