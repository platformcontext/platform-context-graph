"""Compose-backed validation for the synthetic relationship-platform corpus."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
import yaml

from platform_context_graph.core import get_database_manager

pytestmark = pytest.mark.e2e

_BASE_URL_ENV = "PCG_E2E_API_BASE_URL"
_API_KEY_ENV = "PCG_E2E_API_KEY"
_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "relationship_platform"
)
_EXPECTATIONS_PATH = _FIXTURE_ROOT / "expected_relationships.yaml"


@pytest.fixture(scope="module")
def expectations() -> dict[str, object]:
    """Load the synthetic corpus assertion matrix."""

    return yaml.safe_load(_EXPECTATIONS_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def client() -> httpx.Client:
    """Return an authenticated client for the live compose API."""

    base_url = os.getenv(_BASE_URL_ENV)
    api_key = os.getenv(_API_KEY_ENV)
    if not base_url or not api_key:
        pytest.skip(
            f"{_BASE_URL_ENV} and {_API_KEY_ENV} are required for compose API validation"
        )

    with httpx.Client(
        base_url=base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20.0,
    ) as live_client:
        yield live_client


def _get_json(client: httpx.Client, path: str) -> dict[str, object]:
    """Return one decoded API payload."""

    response = client.get(path)
    response.raise_for_status()
    return response.json()


def _repository_id_by_name(client: httpx.Client, *, repository_name: str) -> str:
    """Resolve one canonical repository id from the listing API."""

    repositories_payload = _get_json(client, "/repositories")
    repositories = list(repositories_payload.get("repositories") or [])
    for repository in repositories:
        if str(repository.get("name") or "") != repository_name:
            continue
        repo_id = str(repository.get("id") or repository.get("repo_id") or "")
        if repo_id:
            return repo_id
    pytest.fail(f"Repository '{repository_name}' was not found in the API listing")


def _repository_context_by_name(
    client: httpx.Client, *, repository_name: str
) -> dict[str, object]:
    """Return one repository context payload resolved by repository name."""

    repository_id = _repository_id_by_name(client, repository_name=repository_name)
    return _get_json(
        client,
        f"/repositories/{quote(repository_id, safe='')}/context",
    )


def _single_count(session: object, query: str, **params: object) -> int:
    """Return one integer count from a simple Cypher query."""

    record = session.run(query, **params).single()
    return int(record["count"] if record else 0)


def _assert_repository_relationship(
    session: object,
    *,
    relationship_type: str,
    source: str,
    target: str,
) -> None:
    """Assert one repository-to-repository relationship exists."""

    count = _single_count(
        session,
        f"""
        MATCH (source:Repository {{name: $source}})-[rel:{relationship_type}]->(target:Repository {{name: $target}})
        RETURN count(rel) AS count
        """,
        source=source,
        target=target,
    )
    assert (
        count >= 1
    ), f"Expected repository relationship {source} -[{relationship_type}]-> {target}"


def _assert_platform_relationship(
    session: object,
    *,
    relationship_type: str,
    source: str,
    target: dict[str, object],
) -> None:
    """Assert one repository-to-platform relationship exists."""

    filters = ["platform.kind = $kind"]
    params: dict[str, object] = {
        "kind": str(target["kind"]),
        "source": source,
    }
    if target.get("provider") is not None:
        filters.append("platform.provider = $provider")
        params["provider"] = str(target["provider"])
    if target.get("name") is not None:
        filters.append("platform.name = $name")
        params["name"] = str(target["name"])
    if target.get("environment") is not None:
        filters.append("platform.environment = $environment")
        params["environment"] = str(target["environment"])
    predicate = " AND ".join(filters)
    count = _single_count(
        session,
        f"""
        MATCH (source:Repository {{name: $source}})-[rel:{relationship_type}]->(platform:Platform)
        WHERE {predicate}
        RETURN count(rel) AS count
        """,
        **params,
    )
    assert (
        count >= 1
    ), f"Expected platform relationship {source} -[{relationship_type}]-> {target}"


def _assert_workload_relationship(
    session: object,
    *,
    relationship_type: str,
    source_label: str,
    source_property_key: str,
    source_property_value: str,
    target_label: str,
    target_property_key: str,
    target_property_value: str,
) -> None:
    """Assert one graph relationship exists between workload-layer nodes."""

    count = _single_count(
        session,
        f"""
        MATCH (source:{source_label})-[rel:{relationship_type}]->(target:{target_label})
        WHERE source.{source_property_key} = $source_value
          AND target.{target_property_key} = $target_value
        RETURN count(rel) AS count
        """,
        source_value=source_property_value,
        target_value=target_property_value,
    )
    assert count >= 1, (
        "Expected workload-layer relationship "
        f"{source_label}({source_property_key}={source_property_value}) "
        f"-[{relationship_type}]-> "
        f"{target_label}({target_property_key}={target_property_value})"
    )


def _assert_instance_platform_relationship(
    session: object,
    *,
    relationship_type: str,
    source_instance: str,
    target: dict[str, object],
) -> None:
    """Assert one workload-instance-to-platform relationship exists."""

    filters = ["platform.kind = $kind"]
    params: dict[str, object] = {
        "instance_id": source_instance,
        "kind": str(target["kind"]),
    }
    if target.get("name") is not None:
        filters.append("platform.name = $name")
        params["name"] = str(target["name"])
    if target.get("environment") is not None:
        filters.append("platform.environment = $environment")
        params["environment"] = str(target["environment"])
    predicate = " AND ".join(filters)
    count = _single_count(
        session,
        f"""
        MATCH (source:WorkloadInstance {{id: $instance_id}})-[rel:{relationship_type}]->(platform:Platform)
        WHERE {predicate}
        RETURN count(rel) AS count
        """,
        **params,
    )
    assert (
        count >= 1
    ), f"Expected instance/platform relationship {source_instance} -[{relationship_type}]-> {target}"


def _assert_github_actions_expectations(
    delivery_workflows: dict[str, object], expectations: dict[str, object]
) -> None:
    """Assert GitHub Actions workflow metadata in one repository context."""

    github_actions = dict(delivery_workflows.get("github_actions") or {})
    workflows = list(github_actions.get("workflows") or [])
    workflow_names = {
        str(row.get("name") or "") for row in workflows if isinstance(row, dict)
    }
    workflow_paths = {
        str(row.get("relative_path") or "")
        for row in workflows
        if isinstance(row, dict)
    }
    assert set(expectations.get("workflow_names") or []).issubset(workflow_names)
    assert set(expectations.get("workflow_paths") or []).issubset(workflow_paths)
    assert len(list(github_actions.get("commands") or [])) == int(
        expectations.get("command_count") or 0
    )


def _assert_jenkins_expectations(
    delivery_workflows: dict[str, object], expectations: dict[str, object]
) -> None:
    """Assert Jenkins workflow metadata in one repository context."""

    jenkins_rows = list(delivery_workflows.get("jenkins") or [])
    relative_paths = {
        str(row.get("relative_path") or "")
        for row in jenkins_rows
        if isinstance(row, dict)
    }
    assert set(expectations.get("relative_paths") or []).issubset(relative_paths)
    pipeline_calls = {
        str(call)
        for row in jenkins_rows
        if isinstance(row, dict)
        for call in list(row.get("pipeline_calls") or [])
    }
    shell_commands = {
        str(command)
        for row in jenkins_rows
        if isinstance(row, dict)
        for command in list(row.get("shell_commands") or [])
    }
    assert set(expectations.get("pipeline_calls") or []).issubset(pipeline_calls)
    assert set(expectations.get("shell_commands") or []).issubset(shell_commands)


def _assert_delivery_workflows(
    repository_context: dict[str, object], expectations: dict[str, object]
) -> None:
    """Assert delivery workflow metadata in one repository context payload."""

    delivery_workflows = dict(repository_context.get("delivery_workflows") or {})
    github_actions_expectations = dict(expectations.get("github_actions") or {})
    if github_actions_expectations:
        _assert_github_actions_expectations(
            delivery_workflows, github_actions_expectations
        )
    jenkins_expectations = dict(expectations.get("jenkins") or {})
    if jenkins_expectations:
        _assert_jenkins_expectations(delivery_workflows, jenkins_expectations)


def _assert_delivery_path_expectations(
    repository_context: dict[str, object], expectations: dict[str, object]
) -> None:
    """Assert evidence-backed delivery path details in one repository context."""

    delivery_paths = list(repository_context.get("delivery_paths") or [])
    delivery_modes = {
        str(row.get("delivery_mode") or "")
        for row in delivery_paths
        if isinstance(row, dict)
    }
    deployment_sources = {
        str(source)
        for row in delivery_paths
        if isinstance(row, dict)
        for source in list(row.get("deployment_sources") or [])
    }
    config_sources = {
        str(source)
        for row in delivery_paths
        if isinstance(row, dict)
        for source in list(row.get("config_sources") or [])
    }
    assert set(expectations.get("expected_delivery_modes") or []).issubset(
        delivery_modes
    )
    assert set(expectations.get("expected_local_deployment_sources") or []).issubset(
        deployment_sources
    )
    assert set(expectations.get("expected_local_config_sources") or []).issubset(
        config_sources
    )


def _assert_deployment_artifact_expectations(
    repository_context: dict[str, object], expectations: dict[str, object]
) -> None:
    """Assert selected deployment artifact paths in one repository context."""

    deployment_artifacts = dict(repository_context.get("deployment_artifacts") or {})
    charts = {
        str(row.get("relative_path") or "")
        for row in list(deployment_artifacts.get("charts") or [])
        if isinstance(row, dict)
    }
    cloudformation_resources = {
        str(row.get("file") or "")
        for row in list(
            dict(repository_context.get("infrastructure") or {}).get(
                "cloudformation_resources"
            )
            or []
        )
        if isinstance(row, dict)
    }
    k8s_resources = {
        str(row.get("resource_path") or "")
        for row in list(deployment_artifacts.get("k8s_resources") or [])
        if isinstance(row, dict)
    }
    assert set(expectations.get("chart_paths") or []).issubset(charts)
    assert set(expectations.get("cloudformation_resource_paths") or []).issubset(
        cloudformation_resources
    )
    assert set(expectations.get("k8s_resource_paths") or []).issubset(k8s_resources)


def test_relationship_platform_compose_flow(
    seeded_relationship_platform_graph: None,
    expectations: dict[str, object],
    client: httpx.Client,
) -> None:
    """Validate mapping types and API output against the synthetic corpus."""

    database = get_database_manager()
    driver = database.get_driver()
    with driver.session() as session:
        for row in list(expectations.get("repository_relationships") or []):
            _assert_repository_relationship(
                session,
                relationship_type=str(row["type"]),
                source=str(row["source"]),
                target=str(row["target"]),
            )

        for row in list(expectations.get("platform_relationships") or []):
            _assert_platform_relationship(
                session,
                relationship_type=str(row["type"]),
                source=str(row["source"]),
                target=dict(row["target"]),
            )

        for row in list(expectations.get("workload_relationships") or []):
            relationship_type = str(row["type"])
            if "source_repo" in row:
                _assert_workload_relationship(
                    session,
                    relationship_type=relationship_type,
                    source_label="Repository",
                    source_property_key="name",
                    source_property_value=str(row["source_repo"]),
                    target_label="Workload",
                    target_property_key="id",
                    target_property_value=str(row["target_workload"]),
                )
                continue
            if "source_instance" in row:
                if "target_platform" in row:
                    _assert_instance_platform_relationship(
                        session,
                        relationship_type=relationship_type,
                        source_instance=str(row["source_instance"]),
                        target=dict(row["target_platform"]),
                    )
                    continue
                _assert_workload_relationship(
                    session,
                    relationship_type=relationship_type,
                    source_label="WorkloadInstance",
                    source_property_key="id",
                    source_property_value=str(row["source_instance"]),
                    target_label="Repository" if "target_repo" in row else "Workload",
                    target_property_key="name" if "target_repo" in row else "id",
                    target_property_value=str(
                        row.get("target_repo") or row.get("target_workload")
                    ),
                )
                continue
            _assert_workload_relationship(
                session,
                relationship_type=relationship_type,
                source_label="Workload",
                source_property_key="id",
                source_property_value=str(row["source_workload"]),
                target_label="Workload",
                target_property_key="id",
                target_property_value=str(row["target_workload"]),
            )

    api_expectations = dict(expectations.get("api_expectations") or {})
    repository_name = str(api_expectations["repository_name"])
    repository_context = _repository_context_by_name(
        client, repository_name=repository_name
    )
    deploy_sources = {
        str(row.get("name") or "")
        for row in repository_context.get("deploys_from") or []
        if isinstance(row, dict)
    }
    provisioned_by = {
        str(row.get("name") or "")
        for row in repository_context.get("provisioned_by") or []
        if isinstance(row, dict)
    }
    runtime_platform_kinds = {
        str(row.get("kind") or "")
        for row in repository_context.get("platforms") or []
        if isinstance(row, dict)
    }
    assert set(api_expectations.get("expected_deploy_sources") or []).issubset(
        deploy_sources
    )
    assert set(api_expectations.get("expected_provisioned_by") or []).issubset(
        provisioned_by
    )
    assert set(api_expectations.get("expected_runtime_platform_kinds") or []).issubset(
        runtime_platform_kinds
    )
    _assert_delivery_path_expectations(repository_context, api_expectations)
    _assert_deployment_artifact_expectations(
        repository_context,
        dict(api_expectations.get("expected_local_artifacts") or {}),
    )
    _assert_delivery_workflows(
        repository_context,
        dict(api_expectations.get("expected_delivery_workflows") or {}),
    )

    service_story = _get_json(
        client,
        f"/services/{quote(str(api_expectations['workload_id']), safe='')}/story",
    )
    dependency_names = {
        str(row.get("name") or "")
        for row in (service_story.get("deployment_overview") or {}).get("dependencies")
        or []
        if isinstance(row, dict)
    }
    assert set(api_expectations.get("expected_service_dependencies") or []).issubset(
        dependency_names
    )

    worker_api_expectations = dict(expectations.get("worker_api_expectations") or {})
    worker_context = _repository_context_by_name(
        client,
        repository_name=str(worker_api_expectations["repository_name"]),
    )
    _assert_delivery_workflows(
        worker_context,
        dict(worker_api_expectations.get("expected_delivery_workflows") or {}),
    )
