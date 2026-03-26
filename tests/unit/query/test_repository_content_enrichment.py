from __future__ import annotations

from pathlib import Path

from platform_context_graph.query.repositories.content_enrichment import (
    enrich_repository_context,
)


class _DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _DummyDriver:
    def session(self):
        return _DummySession()


class _DummyDB:
    def get_driver(self):
        return _DummyDriver()


def test_enrich_repository_context_extracts_api_surface_and_hostnames(
    monkeypatch,
    tmp_path: Path,
) -> None:
    helm_repo = tmp_path / "helm-charts"
    values_path = (
        helm_repo / "argocd" / "api-node-boats" / "overlays" / "bg-qa" / "values.yaml"
    )
    values_path.parent.mkdir(parents=True)
    values_path.write_text(
        "ingress:\n  hostnames:\n    - api-node-boats.qa.svc.bgrp.io\n",
        encoding="utf-8",
    )

    file_contents = {
        "server/init/plugins/spec.js": (
            "specPath: path.join(__dirname, '../../../specs/index.yaml'),\n"
            "route: { path: '/_specs' }\n"
        ),
        "specs/index.yaml": (
            "openapi: '3.1.0'\n"
            "paths:\n"
            "  $ref: ./paths/index.yaml\n"
        ),
        "specs/paths/index.yaml": (
            "/_version:\n"
            "  $ref: ./_version.yaml\n"
            "/v3/search:\n"
            "  $ref: ./v3/search.yaml\n"
        ),
        "specs/paths/_version.yaml": (
            "get:\n"
            "  operationId: getVersion\n"
            "  summary: Get version\n"
        ),
        "specs/paths/v3/search.yaml": (
            "get:\n"
            "  operationId: search\n"
            "  summary: Search boats\n"
            "post:\n"
            "  operationId: searchPost\n"
            "  summary: Search boats with body\n"
        ),
        "redocly.yaml": "apis:\n  main:\n    root: ./specs/index.yaml\n",
        "versioning.config.ts": "export const versioning = { defaultVersion: 'v3' };\n",
        "config/qa.json": '{"server":{"hostname":"api-node-boats.qa.bgrp.io"}}',
        "config/production.json": (
            '{"server":{"hostname":"api-node-boats.prod.bgrp.io"}}'
        ),
        "cypress.config.ts": (
            "baseUrl: 'https://api-node-boats.qa.bgrp.io'\n"
            "baseUrl: 'https://api-node-boats.prod.bgrp.io'\n"
            "baseUrl: 'https://api-node-boats.preview.bgrp.io'\n"
        ),
    }

    def _fake_get_file_content(_database, *, repo_id: str, relative_path: str):
        del repo_id
        content = file_contents.get(relative_path)
        if content is None:
            return {"available": False, "content": None}
        return {"available": True, "content": content}

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.content_queries.get_file_content",
        _fake_get_file_content,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.resolve_repository",
        lambda _session, candidate: {
            "id": "repository:r_helm123",
            "name": "helm-charts",
            "path": str(helm_repo),
            "local_path": str(helm_repo),
        }
        if candidate in {"https://github.com/boatsgroup/helm-charts", "helm-charts"}
        else None,
    )

    context = {
        "repository": {
            "id": "repository:r_api_node_boats",
            "name": "api-node-boats",
            "path": "/repos/api-node-boats",
        },
        "deploys_from": [
            {
                "source_repos": "https://github.com/boatsgroup/helm-charts",
                "source_paths": "argocd/api-node-boats/overlays/bg-qa/config.yaml",
            }
        ],
        "limitations": ["dns_unknown"],
    }

    result = enrich_repository_context(_DummyDB(), context)

    assert result["api_surface"]["spec_files"] == [
        {
            "relative_path": "specs/index.yaml",
            "discovered_from": "server/init/plugins/spec.js",
        }
    ]
    assert result["api_surface"]["docs_routes"] == ["/_specs"]
    assert result["api_surface"]["api_versions"] == ["v3"]
    assert result["api_surface"]["endpoint_count"] == 2
    assert result["api_surface"]["endpoints"] == [
        {
            "path": "/_version",
            "methods": ["get"],
            "operation_ids": ["getVersion"],
            "relative_path": "specs/paths/_version.yaml",
        },
        {
            "path": "/v3/search",
            "methods": ["get", "post"],
            "operation_ids": ["search", "searchPost"],
            "relative_path": "specs/paths/v3/search.yaml",
        },
    ]
    assert result["limitations"] == []
    assert result["hostnames"] == [
        {
            "hostname": "api-node-boats.qa.bgrp.io",
            "environment": "qa",
            "source_repo": "api-node-boats",
            "relative_path": "config/qa.json",
            "visibility": "public",
        },
        {
            "hostname": "api-node-boats.prod.bgrp.io",
            "environment": "production",
            "source_repo": "api-node-boats",
            "relative_path": "config/production.json",
            "visibility": "public",
        },
        {
            "hostname": "api-node-boats.preview.bgrp.io",
            "environment": None,
            "source_repo": "api-node-boats",
            "relative_path": "cypress.config.ts",
            "visibility": "public",
        },
        {
            "hostname": "api-node-boats.qa.svc.bgrp.io",
            "environment": "bg-qa",
            "source_repo": "helm-charts",
            "service_repo": "api-node-boats",
            "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
            "visibility": "internal",
        },
    ]
    assert result["observed_config_environments"] == ["qa", "production", "bg-qa"]
