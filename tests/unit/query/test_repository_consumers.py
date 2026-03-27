from __future__ import annotations

from platform_context_graph.query.repositories.content_enrichment_consumers import (
    extract_consumer_repositories,
)


def test_extract_consumer_repositories_excludes_control_plane_matches(
    monkeypatch,
) -> None:
    matches = [
        {
            "repo_id": "repository:r_argocd",
            "relative_path": "applicationsets/api-node/api-node-boats.yaml",
        },
        {
            "repo_id": "repository:r_consumer",
            "relative_path": "server/resources/listings/index.js",
        },
    ]

    monkeypatch.setattr(
        "platform_context_graph.query.content.search_file_content",
        lambda _database, pattern: {"matches": matches if pattern == "api-node-boats" else []},
    )

    repositories = {
        "repository:r_argocd": {
            "id": "repository:r_argocd",
            "name": "iac-eks-argocd",
        },
        "repository:r_consumer": {
            "id": "repository:r_consumer",
            "name": "api-node-brochure",
        },
    }

    result = extract_consumer_repositories(
        database=object(),
        repository={"id": "repository:r_service", "name": "api-node-boats"},
        hostnames=[],
        deployment_artifacts={},
        deploys_from=[],
        discovers_config_in=[],
        provisioned_by=[],
        resolve_related_repo=lambda repo_id: repositories.get(repo_id),
    )

    assert result == [
        {
            "repository": "api-node-brochure",
            "repo_id": "repository:r_consumer",
            "evidence_kinds": ["repository_reference"],
            "matched_values": ["api-node-boats"],
            "sample_paths": ["server/resources/listings/index.js"],
        }
    ]
