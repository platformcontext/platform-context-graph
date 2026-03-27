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
    values_path.write_text(
        "ingress:\n  hostnames:\n    - api-node-boats.qa.svc.bgrp.io\n",
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
    assert result["delivery_workflows"]["github_actions"]["automation_repositories"] == [
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

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment.content_queries.get_file_content",
        lambda _database, *, repo_id, relative_path: {"available": False, "content": None},
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
