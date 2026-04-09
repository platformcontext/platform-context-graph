"""Framework-surfacing coverage for service investigations."""

from __future__ import annotations

import pytest

from platform_context_graph.query.investigation_service import investigate_service


@pytest.fixture
def framework_summary() -> dict[str, object]:
    """Return one bounded framework summary payload for the primary repo."""

    return {
        "frameworks": ["aws", "express", "fastapi", "flask", "gcp", "nextjs", "react"],
        "aws": {
            "module_count": 1,
            "services": ["s3"],
            "client_symbols": ["S3Client"],
            "sample_modules": [
                {
                    "relative_path": "lib/s3.js",
                    "services": ["s3"],
                    "client_symbols": ["S3Client"],
                }
            ],
        },
        "express": {
            "module_count": 1,
            "route_path_count": 2,
            "route_methods": ["GET", "POST"],
            "sample_modules": [
                {
                    "relative_path": "server/routes.js",
                    "route_methods": ["GET", "POST"],
                    "route_paths": ["/health", "/orders"],
                    "server_symbols": ["router"],
                }
            ],
        },
        "fastapi": {
            "module_count": 1,
            "route_path_count": 2,
            "route_methods": ["GET", "POST"],
            "sample_modules": [
                {
                    "relative_path": "app/api.py",
                    "route_methods": ["GET", "POST"],
                    "route_paths": ["/health", "/predict"],
                    "server_symbols": ["app"],
                }
            ],
        },
        "flask": {
            "module_count": 1,
            "route_path_count": 1,
            "route_methods": ["GET"],
            "sample_modules": [
                {
                    "relative_path": "proxy.py",
                    "route_methods": ["GET"],
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
                    "relative_path": "services/vision.js",
                    "services": ["vision"],
                    "client_symbols": ["ImageAnnotatorClient"],
                }
            ],
        },
        "react": {
            "module_count": 4,
            "client_boundary_count": 3,
            "server_boundary_count": 0,
            "shared_boundary_count": 1,
            "component_module_count": 4,
            "hook_module_count": 2,
            "sample_modules": [
                {
                    "relative_path": "app/orders/page.tsx",
                    "boundary": "client",
                    "component_exports": ["default"],
                    "hooks_used": ["useState"],
                }
            ],
        },
        "nextjs": {
            "module_count": 3,
            "page_count": 2,
            "layout_count": 1,
            "route_count": 0,
            "metadata_module_count": 1,
            "route_handler_module_count": 0,
            "client_runtime_count": 2,
            "server_runtime_count": 1,
            "route_verbs": [],
            "sample_modules": [
                {
                    "relative_path": "app/orders/page.tsx",
                    "module_kind": "page",
                    "route_verbs": [],
                    "metadata_exports": "dynamic",
                    "route_segments": ["orders"],
                    "runtime_boundary": "client",
                }
            ],
        },
    }


def test_investigate_service_surfaces_primary_repo_framework_summary(
    monkeypatch: pytest.MonkeyPatch,
    framework_summary: dict[str, object],
) -> None:
    """Investigation responses should expose the primary repo framework profile."""

    def fake_resolve_entity(_database: object, **_kwargs: object) -> dict[str, object]:
        return {
            "matches": [
                {
                    "ref": {
                        "id": "workload:portal-nextjs-platform",
                        "type": "workload",
                        "kind": "service",
                        "name": "portal-nextjs-platform",
                    },
                    "score": 0.99,
                },
                {
                    "ref": {
                        "id": "repository:r_portal12345",
                        "type": "repository",
                        "name": "portal-nextjs-platform",
                    },
                    "score": 0.97,
                },
            ]
        }

    def fake_get_service_story(
        _database: object, **_kwargs: object
    ) -> dict[str, object]:
        return {
            "subject": {
                "id": "workload:portal-nextjs-platform",
                "type": "workload",
                "kind": "service",
                "name": "portal-nextjs-platform",
            },
            "limitations": [],
        }

    def fake_get_repository_context(
        _database: object, **kwargs: object
    ) -> dict[str, object]:
        repo_id = kwargs["repo_id"]
        return {
            "repository": {"id": repo_id, "name": "portal-nextjs-platform"},
            "framework_summary": framework_summary,
        }

    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.entity_resolution_queries.resolve_entity",
        fake_resolve_entity,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.context_queries.get_service_story",
        fake_get_service_story,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.repository_queries.get_repository_story",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.repository_queries.get_repository_context",
        fake_get_repository_context,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.trace_deployment_chain",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.content_queries.search_file_content",
        lambda *_args, **_kwargs: {"matches": []},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service._add_related_repo_details",
        lambda _database, *, widened_repositories: widened_repositories,
    )

    result = investigate_service(
        database=object(),
        service_name="portal-nextjs-platform",
        intent="overview",
    )

    assert result["framework_summary"]["aws"]["services"] == ["s3"]
    assert result["framework_summary"]["express"]["route_path_count"] == 2
    assert result["framework_summary"]["fastapi"]["route_path_count"] == 2
    assert result["framework_summary"]["flask"]["route_path_count"] == 1
    assert result["framework_summary"]["gcp"]["services"] == ["vision"]
    assert result["framework_summary"]["nextjs"]["page_count"] == 2
    assert any(
        line.startswith("Framework and provider evidence shows ")
        for line in result["summary"]
    )
    assert any(
        finding["title"] == "Framework profile detected"
        for finding in result["investigation_findings"]
    )
