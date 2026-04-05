from __future__ import annotations

from typing import Any

from platform_context_graph.query.story_documentation import (
    collect_documentation_evidence,
)


def test_collect_documentation_evidence_prefers_postgres_file_reads_and_search(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_discover_repo_files(
        _database: Any,
        repo_id: str,
        *,
        prefix: str | None = None,
        suffix: str | None = None,
        pattern: str | None = None,
    ) -> list[str]:
        del prefix, suffix, pattern
        if repo_id == "repository:r_api_node_boats":
            return ["README.md", "docs/oncall.md", "src/server.py"]
        return ["argocd/api-node-boats/overlays/bg-qa/values.yaml"]

    def fake_get_file_content(
        _database: Any,
        *,
        repo_id: str,
        relative_path: str,
    ) -> dict[str, Any]:
        calls.append((repo_id, relative_path))
        if relative_path == "README.md":
            return {
                "available": True,
                "repo_id": repo_id,
                "relative_path": relative_path,
                "content": "# API Node Boats\n\nTroubleshooting tips.",
                "source_backend": "postgres",
            }
        if relative_path == "docs/oncall.md":
            return {
                "available": True,
                "repo_id": repo_id,
                "relative_path": relative_path,
                "content": "# On-call\n\nStart with gateway and config.",
                "source_backend": "postgres",
            }
        return {
            "available": False,
            "repo_id": repo_id,
            "relative_path": relative_path,
            "content": None,
            "source_backend": "unavailable",
        }

    def fake_search_file_content(
        _database: Any,
        *,
        pattern: str,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
        artifact_types: list[str] | None = None,
        template_dialects: list[str] | None = None,
        iac_relevant: bool | None = None,
    ) -> dict[str, Any]:
        del pattern, languages, artifact_types, template_dialects, iac_relevant
        return {
            "pattern": "api-node-boats",
            "matches": [
                {
                    "repo_id": repo_ids[0],
                    "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                    "snippet": "hostnames:\n  - api-node-boats.qa.bgrp.io",
                    "source_backend": "postgres",
                }
            ],
        }

    monkeypatch.setattr(
        "platform_context_graph.query.story_documentation.discover_repo_files",
        fake_discover_repo_files,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.story_documentation.content_queries.get_file_content",
        fake_get_file_content,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.story_documentation.content_queries.search_file_content",
        fake_search_file_content,
    )

    evidence = collect_documentation_evidence(
        object(),
        repo_refs=[
            {"id": "repository:r_api_node_boats", "name": "api-node-boats"},
            {"id": "repository:r_helm_charts", "name": "helm-charts"},
        ],
        subject_names=["api-node-boats"],
    )

    assert evidence["file_content"] == [
        {
            "repo_id": "repository:r_api_node_boats",
            "relative_path": "README.md",
            "source_backend": "postgres",
            "title": "API Node Boats",
            "summary": "Troubleshooting tips.",
        },
        {
            "repo_id": "repository:r_api_node_boats",
            "relative_path": "docs/oncall.md",
            "source_backend": "postgres",
            "title": "On-call",
            "summary": "Start with gateway and config.",
        },
    ]
    assert evidence["content_search"][0]["source_backend"] == "postgres"
    assert ("repository:r_api_node_boats", "README.md") in calls
    assert ("repository:r_api_node_boats", "docs/oncall.md") in calls
