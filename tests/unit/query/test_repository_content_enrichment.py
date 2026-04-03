from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from platform_context_graph.query.repositories.content_enrichment import (
    enrich_repository_context,
)


def _build_indexed_file_mocks(
    file_store: dict[tuple[str, str], str],
):
    """Build mock implementations for the indexed_file_discovery functions.

    Args:
        file_store: Mapping of ``(repo_id, relative_path)`` to file content.

    Returns:
        Tuple of ``(discover_repo_files, file_exists, read_file_content,
        read_yaml_file)`` callables backed by the in-memory store.
    """

    def _discover_repo_files(
        _database: Any,
        repo_id: str,
        *,
        prefix: str | None = None,
        suffix: str | None = None,
        pattern: str | None = None,
    ) -> list[str]:
        paths = []
        for rid, rpath in sorted(file_store):
            if rid != repo_id:
                continue
            if prefix and not rpath.startswith(prefix):
                continue
            if suffix and not rpath.endswith(suffix):
                continue
            if pattern and not re.search(pattern, rpath):
                continue
            paths.append(rpath)
        return paths

    def _file_exists(_database: Any, repo_id: str, relative_path: str) -> bool:
        return (repo_id, relative_path) in file_store

    def _read_file_content(
        _database: Any, repo_id: str, relative_path: str
    ) -> str | None:
        return file_store.get((repo_id, relative_path))

    def _read_yaml_file(
        _database: Any, repo_id: str, relative_path: str
    ) -> dict | None:
        content = file_store.get((repo_id, relative_path))
        if content is None:
            return None
        try:
            parsed = yaml.safe_load(content)
        except yaml.YAMLError:
            return None
        return parsed if isinstance(parsed, dict) else None

    return _discover_repo_files, _file_exists, _read_file_content, _read_yaml_file


def _apply_indexed_file_mocks(monkeypatch, file_store):
    """Apply indexed_file_discovery mocks to deployment artifact and workflow modules."""

    fns = _build_indexed_file_mocks(file_store)
    discover, exists, read_content, read_yaml = fns
    _DA = "platform_context_graph.query.repositories.content_enrichment_deployment_artifacts"
    _DAS = "platform_context_graph.query.repositories.content_enrichment_deployment_artifacts_support"
    _WF = "platform_context_graph.query.repositories.content_enrichment_workflows"
    monkeypatch.setattr(f"{_DA}.discover_repo_files", discover)
    monkeypatch.setattr(f"{_DA}.file_exists", exists)
    monkeypatch.setattr(f"{_DA}.read_yaml_file", read_yaml)
    monkeypatch.setattr(f"{_DAS}.discover_repo_files", discover)
    monkeypatch.setattr(f"{_DAS}.file_exists", exists)
    monkeypatch.setattr(f"{_DAS}.read_file_content", read_content)
    monkeypatch.setattr(f"{_DAS}.read_yaml_file", read_yaml)
    monkeypatch.setattr(f"{_WF}.discover_repo_files", discover)
    monkeypatch.setattr(f"{_WF}.read_file_content", read_content)
    monkeypatch.setattr(f"{_WF}.read_yaml_file", read_yaml)


class _DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    def run(self, query, **kwargs):
        """Return empty results for Neo4j file discovery queries."""

        class _EmptyResult:
            def data(self):
                return []

            def single(self):
                return None

        return _EmptyResult()


class _DummyDriver:
    def session(self):
        return _DummySession()


class _DummyDB:
    def get_driver(self):
        return _DummyDriver()


def test_enrich_repository_context_uses_content_service_for_related_config_files(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_get_file_content(_database, *, repo_id: str, relative_path: str):
        calls.append((repo_id, relative_path))
        if (repo_id, relative_path) == (
            "repository:r_api_node_boats",
            "config/qa.json",
        ):
            return {
                "available": True,
                "content": '{"server":{"hostname":"api-node-boats.qa.bgrp.io"}}',
            }
        if (repo_id, relative_path) == (
            "repository:r_helm123",
            "argocd/api-node-boats/overlays/bg-qa/values.yaml",
        ):
            return {
                "available": True,
                "content": (
                    "exposure:\n"
                    "  gateway:\n"
                    "    hostnames:\n"
                    "      - api-node-boats.qa.svc.bgrp.io\n"
                ),
            }
        return {"available": False, "content": None}

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.content_queries.get_file_content",
        _fake_get_file_content,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.extract_related_deployment_artifacts",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.extract_consumer_repositories",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.enrich_workflow_paths",
        lambda **_kwargs: None,
    )

    def _resolve_repository(_session, candidate: str):
        if candidate in {
            "https://github.com/boatsgroup/helm-charts",
            "helm-charts",
        }:
            return {
                "id": "repository:r_helm123",
                "name": "helm-charts",
                "path": "/does/not/matter",
                "local_path": "/does/not/matter",
            }
        return None

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.resolve_repository",
        _resolve_repository,
    )

    result = enrich_repository_context(
        _DummyDB(),
        {
            "repository": {
                "id": "repository:r_api_node_boats",
                "name": "api-node-boats",
                "path": "/does/not/matter",
                "local_path": "/does/not/matter",
            },
            "deploys_from": [
                {
                    "source_repos": "https://github.com/boatsgroup/helm-charts",
                    "source_paths": "argocd/api-node-boats/overlays/bg-qa/config.yaml",
                    "name": "helm-charts",
                }
            ],
            "limitations": ["dns_unknown"],
        },
    )

    assert result["hostnames"] == [
        {
            "hostname": "api-node-boats.qa.bgrp.io",
            "environment": "qa",
            "source_repo": "api-node-boats",
            "relative_path": "config/qa.json",
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
    assert result["observed_config_environments"] == ["qa", "bg-qa"]
    assert (
        "repository:r_api_node_boats",
        "config/qa.json",
    ) in calls
    assert (
        "repository:r_helm123",
        "argocd/api-node-boats/overlays/bg-qa/values.yaml",
    ) in calls


def test_enrich_repository_context_extracts_api_surface_and_hostnames(
    monkeypatch,
    tmp_path: Path,
) -> None:
    service_repo = tmp_path / "api-node-boats"
    (service_repo / ".github" / "workflows").mkdir(parents=True)
    (service_repo / ".github" / "workflows" / "pr-ci-dispatch.yml").write_text(
        "\n".join(
            [
                "name: 'Pull Request: CI Dispatch'",
                "on:",
                "  pull_request:",
                "    types: [opened, synchronize, reopened]",
                "jobs:",
                "  dispatch-api-ci:",
                "    uses: boatsgroup/core-engineering-automation/.github/workflows/node-api-ci.yml@v2",
                "    with:",
                "      environment-name: bg-qa",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (service_repo / ".github" / "workflows" / "pr-command-dispatch.yml").write_text(
        "\n".join(
            [
                "name: 'Pull Request: Command Dispatch'",
                "on:",
                "  issue_comment:",
                "    types: [created]",
                "  workflow_dispatch: {}",
                "jobs:",
                "  dispatch-command:",
                "    uses: boatsgroup/core-engineering-automation/.github/workflows/node-api-command-processing.yml@v2",
                "    with:",
                "      automation-repo: boatsgroup/core-engineering-automation",
                "",
            ]
        ),
        encoding="utf-8",
    )

    helm_repo = tmp_path / "helm-charts"
    values_path = (
        helm_repo / "argocd" / "api-node-boats" / "overlays" / "bg-qa" / "values.yaml"
    )
    values_path.parent.mkdir(parents=True)
    config_path = (
        helm_repo / "argocd" / "api-node-boats" / "overlays" / "bg-qa" / "config.yaml"
    )
    config_path.write_text(
        "\n".join(
            [
                "addon: api-node-boats",
                "environment: bg-qa",
                "git:",
                "  repoURL: https://github.com/boatsgroup/helm-charts",
                "  overlayPath: argocd/api-node-boats/overlays/bg-qa",
                "helm:",
                "  repoURL: boatsgroup.pe.jfrog.io",
                "  chart: bg-helm/api-node-template",
                '  version: "0.2.1"',
                "  namespace: api-node",
                "  releaseName: api-node-boats",
                "",
            ]
        ),
        encoding="utf-8",
    )
    values_path.write_text(
        "\n".join(
            [
                "image:",
                "  repository: 048922418463.dkr.ecr.us-east-1.amazonaws.com/api-node-boats",
                "  tag: 3.21.0",
                "service:",
                "  port: 3081",
                "exposure:",
                "  gateway:",
                "    enabled: true",
                "    hostnames:",
                "      - api-node-boats.qa.svc.bgrp.io",
                "    parentRefs:",
                "      - name: envoy-internal",
                "",
            ]
        ),
        encoding="utf-8",
    )
    base_values_path = helm_repo / "argocd" / "api-node-boats" / "base" / "values.yaml"
    base_values_path.parent.mkdir(parents=True)
    (
        helm_repo / "argocd" / "api-node-boats" / "base" / "kustomization.yaml"
    ).write_text(
        "\n".join(
            [
                "apiVersion: kustomize.config.k8s.io/v1beta1",
                "kind: Kustomization",
                "resources:",
                "  - xirsarole.yaml",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (helm_repo / "argocd" / "api-node-boats" / "base" / "xirsarole.yaml").write_text(
        "\n".join(
            [
                "apiVersion: aws.bgrp.io/v1alpha1",
                "kind: XIRSARole",
                "metadata:",
                "  name: api-node-boats",
                "spec:",
                "  policyDocument:",
                "    Statement:",
                "      - Resource:",
                "          - arn:aws:ssm:AWS_REGION:AWS_ACCOUNT_ID:parameter/configd/api-node-boats/*",
                "          - arn:aws:ssm:AWS_REGION:AWS_ACCOUNT_ID:parameter/api/api-node-boats/*",
                "",
            ]
        ),
        encoding="utf-8",
    )
    base_values_path.write_text(
        "service:\n  port: 3081\n",
        encoding="utf-8",
    )
    (
        helm_repo
        / "argocd"
        / "api-node-boats"
        / "overlays"
        / "bg-qa"
        / "kustomization.yaml"
    ).write_text(
        "\n".join(
            [
                "apiVersion: kustomize.config.k8s.io/v1beta1",
                "kind: Kustomization",
                "resources:",
                "  - ../../base",
                "patches:",
                "  - path: xirsarole-patch.yaml",
                "    target:",
                "      kind: XIRSARole",
                "      name: api-node-boats",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (
        helm_repo
        / "argocd"
        / "api-node-boats"
        / "overlays"
        / "bg-qa"
        / "xirsarole-patch.yaml"
    ).write_text(
        "spec:\n  clusterName: bg-qa\n",
        encoding="utf-8",
    )
    automation_repo = tmp_path / "core-engineering-automation"
    (automation_repo / ".github" / "workflows").mkdir(parents=True)
    (
        automation_repo / ".github" / "workflows" / "node-api-command-processing.yml"
    ).write_text(
        "\n".join(
            [
                "name: 'Node.js API: Command Processing'",
                "env:",
                "  VALID_COMMANDS_DATA: |",
                "    [",
                '      {"name":"deploy","description":"Dispatch Node.js API CD"},',
                '      {"name":"deploy-eks","description":"Build, push to ECR, and update helm-charts for ArgoCD EKS deployment"},',
                '      {"name":"push-ecr","description":"Build and push Docker image to ECR (no ECS deployment)"}',
                "    ]",
                "jobs:",
                "  dispatch-api-cd:",
                "    if: needs.parse-command.outputs.command == 'deploy'",
                "    uses: ./.github/workflows/node-api-cd.yml",
                "  deploy-to-eks:",
                "    if: needs.parse-command.outputs.command == 'deploy-eks'",
                "    uses: ./.github/workflows/node-api-deploy-eks.yml",
                "  push-to-ecr:",
                "    if: needs.parse-command.outputs.command == 'push-ecr'",
                "    uses: ./.github/workflows/node-api-ecr-push.yml",
                "",
            ]
        ),
        encoding="utf-8",
    )
    terraform_repo = tmp_path / "terraform-stack-node10"
    (terraform_repo / "shared").mkdir(parents=True)
    (terraform_repo / "shared" / "iam.tf").write_text(
        "\n".join(
            [
                'data "aws_iam_policy_document" "api_node_boats" {',
                "  statement {",
                '    resources = ["/configd/api-node-boats/*", "/api/api-node-boats/*", "/configd/elasticache/*"]',
                "  }",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Build indexed file store for deployment-artifact and workflow enrichment
    # (replaces filesystem access in the converted modules).
    _helm_id = "repository:r_helm123"
    _tf_id = "repository:r_terraform123"
    _svc_id = "repository:r_api_node_boats"
    _auto_id = "repository:r_automation123"
    _indexed_store: dict[tuple[str, str], str] = {}
    for _repo_path, _repo_id in [
        (helm_repo, _helm_id),
        (terraform_repo, _tf_id),
        (service_repo, _svc_id),
        (automation_repo, _auto_id),
    ]:
        if _repo_path.exists():
            for _fp in sorted(_repo_path.rglob("*")):
                if _fp.is_file():
                    _rel = str(_fp.relative_to(_repo_path))
                    try:
                        _indexed_store[(_repo_id, _rel)] = _fp.read_text(
                            encoding="utf-8"
                        )
                    except UnicodeDecodeError:
                        pass
    _apply_indexed_file_mocks(monkeypatch, _indexed_store)

    file_contents = {
        "server/init/plugins/spec.js": (
            "specPath: path.join(__dirname, '../../../specs/index.yaml'),\n"
            "route: { path: '/_specs' }\n"
        ),
        "specs/index.yaml": (
            "openapi: '3.1.0'\n" "paths:\n" "  $ref: ./paths/index.yaml\n"
        ),
        "specs/paths/index.yaml": (
            "/_version:\n"
            "  $ref: ./_version.yaml\n"
            "/v3/search:\n"
            "  $ref: ./v3/search.yaml\n"
        ),
        "specs/paths/_version.yaml": (
            "get:\n" "  operationId: getVersion\n" "  summary: Get version\n"
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
        "argocd/api-node-boats/overlays/bg-qa/values.yaml": (
            "image:\n"
            "  repository: 048922418463.dkr.ecr.us-east-1.amazonaws.com/api-node-boats\n"
            "  tag: 3.21.0\n"
            "service:\n"
            "  port: 3081\n"
            "exposure:\n"
            "  gateway:\n"
            "    enabled: true\n"
            "    hostnames:\n"
            "      - api-node-boats.qa.svc.bgrp.io\n"
            "    parentRefs:\n"
            "      - name: envoy-internal\n"
        ),
        "argocd/api-node-boats/base/values.yaml": "service:\n  port: 3081\n",
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

    def _fake_search_file_content(_database, *, pattern: str, **_kwargs):
        if pattern == "api-node-boats":
            return {
                "matches": [
                    {
                        "repo_id": "repository:r_platform123",
                        "relative_path": "server/resources/listing/index.js",
                        "snippet": "const boatsApiClient = require('@dmm/api-node-boats-client');",
                    },
                    {
                        "repo_id": "repository:r_brochure123",
                        "relative_path": "server/resources/listings/index.js",
                        "snippet": "const boatsApi = require('@dmm/dmm-clients/lib/api-node-boats');",
                    },
                ]
            }
        if pattern == "api-node-boats.qa.bgrp.io":
            return {
                "matches": [
                    {
                        "repo_id": "repository:r_yachtworld123",
                        "relative_path": "group_vars/qa/api.yml",
                        "snippet": "listing_api_hostname: https://api-node-boats.qa.bgrp.io",
                    }
                ]
            }
        if pattern == "/configd/api-node-boats/":
            return {
                "matches": [
                    {
                        "repo_id": "repository:r_boattrader123",
                        "relative_path": "shared/iam.tf",
                        "snippet": 'values = ["/configd/api-node-boats/*"]',
                    }
                ]
            }
        return {"matches": []}

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.content_queries.search_file_content",
        _fake_search_file_content,
    )

    def _resolve_repository(_session, candidate: str):
        if candidate in {
            "https://github.com/boatsgroup/core-engineering-automation",
            "boatsgroup/core-engineering-automation",
            "core-engineering-automation",
        }:
            return {
                "id": "repository:r_automation123",
                "name": "core-engineering-automation",
                "path": str(automation_repo),
                "local_path": str(automation_repo),
            }
        if candidate in {
            "https://github.com/boatsgroup/helm-charts",
            "helm-charts",
        }:
            return {
                "id": "repository:r_helm123",
                "name": "helm-charts",
                "path": str(helm_repo),
                "local_path": str(helm_repo),
            }
        if candidate in {"repository:r_platform123", "api-node-platform"}:
            return {
                "id": "repository:r_platform123",
                "name": "api-node-platform",
                "path": str(tmp_path / "api-node-platform"),
                "local_path": str(tmp_path / "api-node-platform"),
            }
        if candidate in {"repository:r_brochure123", "api-node-brochure"}:
            return {
                "id": "repository:r_brochure123",
                "name": "api-node-brochure",
                "path": str(tmp_path / "api-node-brochure"),
                "local_path": str(tmp_path / "api-node-brochure"),
            }
        if candidate in {"repository:r_yachtworld123", "automate-yachtworld"}:
            return {
                "id": "repository:r_yachtworld123",
                "name": "automate-yachtworld",
                "path": str(tmp_path / "automate-yachtworld"),
                "local_path": str(tmp_path / "automate-yachtworld"),
            }
        if candidate in {"repository:r_boattrader123", "terraform-stack-boattrader"}:
            return {
                "id": "repository:r_boattrader123",
                "name": "terraform-stack-boattrader",
                "path": str(tmp_path / "terraform-stack-boattrader"),
                "local_path": str(tmp_path / "terraform-stack-boattrader"),
            }
        if candidate in {"repository:r_terraform123", "terraform-stack-node10"}:
            return {
                "id": "repository:r_terraform123",
                "name": "terraform-stack-node10",
                "path": str(terraform_repo),
                "local_path": str(terraform_repo),
            }
        return None

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.resolve_repository",
        _resolve_repository,
    )

    context = {
        "repository": {
            "id": "repository:r_api_node_boats",
            "name": "api-node-boats",
            "path": str(service_repo),
            "local_path": str(service_repo),
        },
        "platforms": [
            {
                "id": "platform:eks:aws:cluster/bg-qa:bg-qa:none",
                "kind": "eks",
                "environment": "bg-qa",
            },
            {
                "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                "kind": "ecs",
                "environment": "prod",
            },
        ],
        "deploys_from": [
            {
                "source_repos": "https://github.com/boatsgroup/helm-charts",
                "source_paths": "argocd/api-node-boats/overlays/bg-qa/config.yaml",
                "name": "helm-charts",
            }
        ],
        "provisioned_by": [
            {
                "id": "repository:r_terraform123",
                "name": "terraform-stack-node10",
                "relationship_type": "PROVISIONED_BY",
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
    assert result["delivery_workflows"]["github_actions"][
        "automation_repositories"
    ] == [
        {
            "repository": "boatsgroup/core-engineering-automation",
            "owner": "boatsgroup",
            "name": "core-engineering-automation",
            "ref": "v2",
        }
    ]
    assert result["delivery_workflows"]["github_actions"]["commands"] == [
        {
            "command": "deploy",
            "description": "Dispatch Node.js API CD",
            "workflow": "node-api-cd.yml",
            "workflow_path": ".github/workflows/node-api-cd.yml",
            "delivery_mode": "continuous_deployment",
            "automation_repository": "boatsgroup/core-engineering-automation",
        },
        {
            "command": "deploy-eks",
            "description": "Build, push to ECR, and update helm-charts for ArgoCD EKS deployment",
            "workflow": "node-api-deploy-eks.yml",
            "workflow_path": ".github/workflows/node-api-deploy-eks.yml",
            "delivery_mode": "eks_gitops",
            "automation_repository": "boatsgroup/core-engineering-automation",
        },
        {
            "command": "push-ecr",
            "description": "Build and push Docker image to ECR (no ECS deployment)",
            "workflow": "node-api-ecr-push.yml",
            "workflow_path": ".github/workflows/node-api-ecr-push.yml",
            "delivery_mode": "image_build_push",
            "automation_repository": "boatsgroup/core-engineering-automation",
        },
    ]
    assert result["delivery_paths"] == [
        {
            "path_kind": "gitops",
            "controller": "github_actions",
            "delivery_mode": "eks_gitops",
            "commands": ["deploy-eks"],
            "supporting_workflows": ["node-api-deploy-eks.yml"],
            "automation_repositories": ["boatsgroup/core-engineering-automation"],
            "platform_kinds": ["eks"],
            "platforms": ["platform:eks:aws:cluster/bg-qa:bg-qa:none"],
            "deployment_sources": ["helm-charts"],
            "config_sources": [],
            "provisioning_repositories": [],
            "environments": ["bg-qa"],
            "summary": (
                "GitHub Actions drives a GitOps deployment path through helm-charts "
                "onto EKS platforms."
            ),
        },
        {
            "path_kind": "direct",
            "controller": "github_actions",
            "delivery_mode": "continuous_deployment",
            "commands": ["deploy", "push-ecr"],
            "supporting_workflows": [
                "node-api-cd.yml",
                "node-api-ecr-push.yml",
            ],
            "automation_repositories": ["boatsgroup/core-engineering-automation"],
            "platform_kinds": ["ecs"],
            "platforms": ["platform:ecs:aws:cluster/node10:prod:us-east-1"],
            "deployment_sources": [],
            "config_sources": [],
            "provisioning_repositories": ["terraform-stack-node10"],
            "environments": ["prod"],
            "summary": (
                "GitHub Actions drives a direct deployment path through "
                "terraform-stack-node10 onto ECS platforms."
            ),
        },
    ]
    assert result["consumer_repositories"] == [
        {
            "repository": "api-node-brochure",
            "repo_id": "repository:r_brochure123",
            "evidence_kinds": ["repository_reference"],
            "matched_values": ["api-node-boats"],
            "sample_paths": ["server/resources/listings/index.js"],
        },
        {
            "repository": "api-node-platform",
            "repo_id": "repository:r_platform123",
            "evidence_kinds": ["repository_reference"],
            "matched_values": ["api-node-boats"],
            "sample_paths": ["server/resources/listing/index.js"],
        },
        {
            "repository": "automate-yachtworld",
            "repo_id": "repository:r_yachtworld123",
            "evidence_kinds": ["hostname_reference"],
            "matched_values": ["api-node-boats.qa.bgrp.io"],
            "sample_paths": ["group_vars/qa/api.yml"],
        },
        {
            "repository": "terraform-stack-boattrader",
            "repo_id": "repository:r_boattrader123",
            "evidence_kinds": ["config_path_reference"],
            "matched_values": ["/configd/api-node-boats/"],
            "sample_paths": ["shared/iam.tf"],
        },
    ]
    assert result["deployment_artifacts"] == {
        "charts": [
            {
                "repo_url": "boatsgroup.pe.jfrog.io",
                "chart": "bg-helm/api-node-template",
                "version": "0.2.1",
                "release_name": "api-node-boats",
                "namespace": "api-node",
                "source_repo": "helm-charts",
                "relative_path": "argocd/api-node-boats/overlays/bg-qa/config.yaml",
                "environment": "bg-qa",
            }
        ],
        "images": [
            {
                "repository": "048922418463.dkr.ecr.us-east-1.amazonaws.com/api-node-boats",
                "tag": "3.21.0",
                "source_repo": "helm-charts",
                "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                "environment": "bg-qa",
            }
        ],
        "service_ports": [
            {
                "port": "3081",
                "source_repo": "helm-charts",
                "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                "environment": "bg-qa",
            },
            {
                "port": "3081",
                "source_repo": "helm-charts",
                "relative_path": "argocd/api-node-boats/base/values.yaml",
                "environment": None,
            },
        ],
        "gateways": [
            {
                "name": "envoy-internal",
                "source_repo": "helm-charts",
                "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                "environment": "bg-qa",
            }
        ],
        "kustomize_resources": [
            {
                "resource_path": "argocd/api-node-boats/base/xirsarole.yaml",
                "kind": "XIRSARole",
                "name": "api-node-boats",
                "source_repo": "helm-charts",
                "relative_path": "argocd/api-node-boats/base/kustomization.yaml",
                "environment": None,
            }
        ],
        "kustomize_patches": [
            {
                "patch_path": "argocd/api-node-boats/overlays/bg-qa/xirsarole-patch.yaml",
                "target_kind": "XIRSARole",
                "target_name": "api-node-boats",
                "source_repo": "helm-charts",
                "relative_path": "argocd/api-node-boats/overlays/bg-qa/kustomization.yaml",
                "environment": "bg-qa",
            }
        ],
        "config_paths": [
            {
                "path": "/configd/api-node-boats/*",
                "source_repo": "helm-charts",
                "relative_path": "argocd/api-node-boats/base/xirsarole.yaml",
                "environment": None,
            },
            {
                "path": "/api/api-node-boats/*",
                "source_repo": "helm-charts",
                "relative_path": "argocd/api-node-boats/base/xirsarole.yaml",
                "environment": None,
            },
            {
                "path": "/configd/api-node-boats/*",
                "source_repo": "terraform-stack-node10",
                "relative_path": "shared/iam.tf",
                "environment": None,
            },
            {
                "path": "/api/api-node-boats/*",
                "source_repo": "terraform-stack-node10",
                "relative_path": "shared/iam.tf",
                "environment": None,
            },
            {
                "path": "/configd/elasticache/*",
                "source_repo": "terraform-stack-node10",
                "relative_path": "shared/iam.tf",
                "environment": None,
            },
        ],
    }


def test_enrich_repository_context_extracts_jenkins_pipeline_hints(
    monkeypatch,
    tmp_path: Path,
) -> None:
    service_repo = tmp_path / "api-node-whisper"
    service_repo.mkdir()
    (service_repo / "Jenkinsfile").write_text(
        "\n".join(
            [
                "@Library('pipelines') _",
                "",
                "pipelinePM2(",
                "  use_configd: true,",
                "  entry_point: 'dist/api-node-whisper.js',",
                "  pre_deploy: { pipe, params ->",
                "    sh 'echo migrate'",
                "  }",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )

    _svc_id = "repository:r_api_node_whisper"
    _indexed_store: dict[tuple[str, str], str] = {}
    for _fp in sorted(service_repo.rglob("*")):
        if _fp.is_file():
            _rel = str(_fp.relative_to(service_repo))
            try:
                _indexed_store[(_svc_id, _rel)] = _fp.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                pass
    _apply_indexed_file_mocks(monkeypatch, _indexed_store)

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.content_queries.get_file_content",
        lambda _database, *, repo_id, relative_path: {
            "available": False,
            "content": None,
        },
    )

    context = {
        "repository": {
            "id": "repository:r_api_node_whisper",
            "name": "api-node-whisper",
            "path": str(service_repo),
            "local_path": str(service_repo),
        },
        "limitations": [],
    }

    result = enrich_repository_context(_DummyDB(), context)

    assert result["delivery_workflows"]["jenkins"] == [
        {
            "relative_path": "Jenkinsfile",
            "shared_libraries": ["pipelines"],
            "pipeline_calls": ["pipelinePM2"],
            "shell_commands": ["echo migrate"],
            "ansible_playbook_hints": [],
            "entry_points": ["dist/api-node-whisper.js"],
            "use_configd": True,
            "has_pre_deploy": True,
        }
    ]


def test_enrich_repository_context_extracts_nested_workflow_command_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    service_repo = tmp_path / "api-node-boats"
    (service_repo / ".github" / "workflows").mkdir(parents=True)
    (service_repo / ".github" / "workflows" / "pr-command-dispatch.yml").write_text(
        "\n".join(
            [
                "name: 'Pull Request: Command Dispatch'",
                "on:",
                "  issue_comment:",
                "    types: [created]",
                "jobs:",
                "  dispatch-command:",
                "    uses: boatsgroup/core-engineering-automation/.github/workflows/node-api-command-processing.yml@v2",
            ]
        ),
        encoding="utf-8",
    )
    automation_repo = tmp_path / "core-engineering-automation"
    (automation_repo / ".github" / "workflows").mkdir(parents=True)
    (
        automation_repo / ".github" / "workflows" / "node-api-command-processing.yml"
    ).write_text(
        "\n".join(
            [
                "name: 'Node.js API: Command Processing'",
                "jobs:",
                "  parse-command:",
                "    steps:",
                "      - name: Post Command Feedback",
                "        env:",
                "          VALID_COMMANDS_DATA: |",
                "            [",
                '              {"name":"deploy-eks","description":"Build, push to ECR, and update helm-charts for ArgoCD EKS deployment"},',
                '              {"name":"rollback-eks","description":"Rollback EKS deployment to a known ECR image tag"},',
                "            ]",
                "  deploy-to-eks:",
                "    if: needs.parse-command.outputs.command == 'deploy-eks'",
                "    uses: ./.github/workflows/node-api-deploy-eks.yml",
                "  rollback-eks:",
                "    if: needs.parse-command.outputs.command == 'rollback-eks'",
                "    uses: ./.github/workflows/node-api-rollback-eks.yml",
            ]
        ),
        encoding="utf-8",
    )

    _svc_id = "repository:r_api_node_boats"
    _auto_id = "repository:r_automation123"
    _indexed_store: dict[tuple[str, str], str] = {}
    for _repo_path, _repo_id in [
        (service_repo, _svc_id),
        (automation_repo, _auto_id),
    ]:
        for _fp in sorted(_repo_path.rglob("*")):
            if _fp.is_file():
                _rel = str(_fp.relative_to(_repo_path))
                try:
                    _indexed_store[(_repo_id, _rel)] = _fp.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    pass
    _apply_indexed_file_mocks(monkeypatch, _indexed_store)

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.content_queries.get_file_content",
        lambda _database, *, repo_id, relative_path: {
            "available": False,
            "content": None,
        },
    )

    def _resolve_repository(_session, candidate: str):
        if candidate in {
            "https://github.com/boatsgroup/core-engineering-automation",
            "boatsgroup/core-engineering-automation",
            "core-engineering-automation",
        }:
            return {
                "id": "repository:r_automation123",
                "name": "core-engineering-automation",
                "path": str(automation_repo),
                "local_path": str(automation_repo),
            }
        return None

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.resolve_repository",
        _resolve_repository,
    )

    result = enrich_repository_context(
        _DummyDB(),
        {
            "repository": {
                "id": "repository:r_api_node_boats",
                "name": "api-node-boats",
                "path": str(service_repo),
                "local_path": str(service_repo),
            },
            "limitations": [],
        },
    )

    assert result["delivery_workflows"]["github_actions"]["commands"] == [
        {
            "command": "deploy-eks",
            "description": "Build, push to ECR, and update helm-charts for ArgoCD EKS deployment",
            "workflow": "node-api-deploy-eks.yml",
            "workflow_path": ".github/workflows/node-api-deploy-eks.yml",
            "delivery_mode": "eks_gitops",
            "automation_repository": "boatsgroup/core-engineering-automation",
        },
        {
            "command": "rollback-eks",
            "description": "Rollback EKS deployment to a known ECR image tag",
            "workflow": "node-api-rollback-eks.yml",
            "workflow_path": ".github/workflows/node-api-rollback-eks.yml",
            "delivery_mode": "eks_gitops_rollback",
            "automation_repository": "boatsgroup/core-engineering-automation",
        },
    ]


def test_enrich_repository_context_adds_controller_driven_paths(
    monkeypatch,
    fixture_repo: Path,
) -> None:
    _repo_id = "repository:r_ansible_jenkins_automation"
    _indexed_store: dict[tuple[str, str], str] = {}
    for _fp in sorted(fixture_repo.rglob("*")):
        if _fp.is_file():
            _rel = str(_fp.relative_to(fixture_repo))
            try:
                _indexed_store[(_repo_id, _rel)] = _fp.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                pass
    _apply_indexed_file_mocks(monkeypatch, _indexed_store)

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.content_queries.get_file_content",
        lambda _database, *, repo_id, relative_path: {
            "available": False,
            "content": None,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.content_queries.search_file_content",
        lambda _database, **_kwargs: {"matches": []},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.resolve_repository",
        lambda _session, candidate: None,
    )

    result = enrich_repository_context(
        _DummyDB(),
        {
            "repository": {
                "id": "repository:r_ansible_jenkins_automation",
                "name": "ansible-jenkins-automation",
                "path": str(fixture_repo),
                "local_path": str(fixture_repo),
            },
            "platforms": [
                {
                    "id": "platform:vmware:none:mws:prod:none",
                    "kind": "vm",
                    "environment": "prod",
                }
            ],
            "provisioned_by": [{"name": "terraform-stack-mws"}],
        },
    )

    assert result["delivery_workflows"]["jenkins"] == [
        {
            "relative_path": "Jenkinsfile",
            "shared_libraries": [],
            "pipeline_calls": ["pipelineDeploy"],
            "shell_commands": ["./scripts/deploy.sh"],
            "ansible_playbook_hints": [],
            "entry_points": [],
            "use_configd": None,
            "has_pre_deploy": False,
        }
    ]
    assert result["controller_driven_paths"] == [
        {
            "controller_kind": "jenkins",
            "controller_repository": None,
            "automation_kind": "ansible",
            "automation_repository": None,
            "entry_points": ["deploy.yml"],
            "target_descriptors": ["mws", "prod"],
            "runtime_family": "wordpress_website_fleet",
            "supporting_repositories": ["terraform-stack-mws"],
            "confidence": "high",
            "explanation": (
                "jenkins controller Jenkinsfile invokes ansible entry points "
                "deploy.yml targeting mws, prod for wordpress_website_fleet "
                "with support from terraform-stack-mws."
            ),
        }
    ]
    assert result["delivery_paths"] == [
        {
            "path_kind": "direct",
            "controller": "jenkins",
            "delivery_mode": "jenkins_pipeline",
            "commands": [],
            "supporting_workflows": ["Jenkinsfile"],
            "automation_repositories": [],
            "platform_kinds": ["vm"],
            "platforms": ["platform:vmware:none:mws:prod:none"],
            "deployment_sources": [],
            "config_sources": [],
            "provisioning_repositories": ["terraform-stack-mws"],
            "environments": ["prod"],
            "summary": (
                "Jenkins drives a direct deployment path through "
                "terraform-stack-mws onto VM platforms."
            ),
        }
    ]
