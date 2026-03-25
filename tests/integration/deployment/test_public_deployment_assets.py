from __future__ import annotations

import os
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CHART_DIR = REPO_ROOT / "deploy" / "helm" / "platform-context-graph"
MINIMAL_MANIFEST_DIR = REPO_ROOT / "deploy" / "manifests" / "minimal"
ARGOCD_BASE_DIR = REPO_ROOT / "deploy" / "argocd" / "base"
ARGOCD_AWS_DIR = REPO_ROOT / "deploy" / "argocd" / "overlays" / "aws"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yaml"
COMPOSE_TEMPLATE_FILE = REPO_ROOT / "docker-compose.template.yml"
OTEL_COLLECTOR_CONFIG_FILE = (
    REPO_ROOT / "deploy" / "observability" / "otel-collector-config.yaml"
)
DASHBOARD_FILE = (
    REPO_ROOT
    / "deploy"
    / "grafana"
    / "dashboards"
    / "platform-context-graph-observability.json"
)
MCP_EXAMPLE_FILE = REPO_ROOT / ".mcp.json.example"


def _render_chart(*args: str) -> list[dict]:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("helm is required for deployment asset rendering tests")

    result = subprocess.run(
        [helm, "template", "platform-context-graph", str(CHART_DIR), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _kinds(docs: list[dict]) -> list[str]:
    return [str(doc["kind"]) for doc in docs]


def _compose_service_envs(service: dict) -> dict[str, str]:
    environment = service.get("environment", {})
    if isinstance(environment, dict):
        return {str(key): str(value) for key, value in environment.items()}

    return {
        env["name"]: env["value"]
        for env in environment
        if isinstance(env, dict) and "name" in env and "value" in env
    }


def test_public_deployment_layout_exists() -> None:
    assert CHART_DIR.exists()
    assert MINIMAL_MANIFEST_DIR.exists()
    assert ARGOCD_BASE_DIR.exists()
    assert ARGOCD_AWS_DIR.exists()
    assert MCP_EXAMPLE_FILE.exists()


def test_default_chart_renders_api_deployment_and_worker_statefulset() -> None:
    docs = _render_chart()
    kinds = _kinds(docs)

    assert "StatefulSet" in kinds
    assert "Deployment" in kinds
    assert "Service" in kinds
    assert "Ingress" not in kinds
    assert "HTTPRoute" not in kinds
    metadata_names = {doc.get("metadata", {}).get("name", "") for doc in docs}
    assert not any(name.endswith("neo4j") or name == "neo4j" for name in metadata_names)
    assert not any(name.endswith("-scripts") for name in metadata_names)

    deployment = next(doc for doc in docs if doc["kind"] == "Deployment")
    deployment_pod_spec = deployment["spec"]["template"]["spec"]
    deployment_container = next(
        container
        for container in deployment_pod_spec["containers"]
        if container["name"] == "platform-context-graph"
    )

    worker_statefulset = next(doc for doc in docs if doc["kind"] == "StatefulSet")
    worker_pod_spec = worker_statefulset["spec"]["template"]["spec"]
    worker_container = next(
        container
        for container in worker_pod_spec["containers"]
        if container["name"] == "repo-sync"
    )

    assert deployment_pod_spec.get("initContainers", []) == []
    assert deployment_container["command"] == [
        "pcg",
        "serve",
        "start",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
    ]
    assert worker_container["command"] == ["pcg", "internal", "repo-sync-loop"]
    assert worker_statefulset["spec"]["serviceName"] == "platform-context-graph-ingester"
    assert worker_statefulset["spec"]["selector"]["matchLabels"] == {
        "app.kubernetes.io/name": "platform-context-graph",
        "app.kubernetes.io/instance": "platform-context-graph",
        "app.kubernetes.io/component": "ingester",
    }

    ingester_service = next(
        doc
        for doc in docs
        if doc["kind"] == "Service"
        and doc["metadata"]["name"] == "platform-context-graph-ingester"
    )
    assert ingester_service["spec"]["clusterIP"] == "None"
    assert ingester_service["spec"]["selector"] == {
        "app.kubernetes.io/name": "platform-context-graph",
        "app.kubernetes.io/instance": "platform-context-graph",
        "app.kubernetes.io/component": "ingester",
    }

    api_env_names = {env["name"] for env in deployment_container.get("env", [])}
    worker_env_names = {env["name"] for env in worker_container.get("env", [])}
    api_volume_mounts = {
        volume_mount["mountPath"]
        for volume_mount in deployment_container.get("volumeMounts", [])
    }
    worker_volume_mounts = {
        volume_mount["mountPath"]
        for volume_mount in worker_container.get("volumeMounts", [])
    }

    assert "PCG_REPOSITORY_RULES_JSON" not in api_env_names
    assert "PCG_REPOS_DIR" not in api_env_names
    assert "PCG_REPOSITORY_RULES_JSON" in worker_env_names
    assert "PCG_REPOS_DIR" in worker_env_names
    assert "/data" not in api_volume_mounts
    assert "/data" in worker_volume_mounts


def test_chart_can_render_ingress() -> None:
    docs = _render_chart(
        "--set",
        "exposure.ingress.enabled=true",
        "--set",
        "exposure.ingress.className=nginx",
        "--set",
        "exposure.ingress.hosts[0].host=pcg.example.com",
        "--set",
        "exposure.ingress.hosts[0].paths[0].path=/",
        "--set",
        "exposure.ingress.hosts[0].paths[0].pathType=Prefix",
    )
    assert "Ingress" in _kinds(docs)


def test_chart_can_render_gateway_api_route() -> None:
    docs = _render_chart(
        "--set",
        "exposure.gateway.enabled=true",
        "--set",
        "exposure.gateway.hostnames[0]=pcg.example.com",
        "--set",
        "exposure.gateway.parentRefs[0].name=shared-gateway",
    )
    assert "HTTPRoute" in _kinds(docs)


def test_chart_rejects_enabling_ingress_and_gateway_together() -> None:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("helm is required for deployment asset rendering tests")

    result = subprocess.run(
        [
            helm,
            "template",
            "platform-context-graph",
            str(CHART_DIR),
            "--set",
            "exposure.ingress.enabled=true",
            "--set",
            "exposure.gateway.enabled=true",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


def test_minimal_manifest_uses_external_neo4j_only() -> None:
    files = sorted(MINIMAL_MANIFEST_DIR.glob("*.yaml"))
    assert files

    rendered = "\n".join(path.read_text() for path in files)
    lowered = rendered.lower()
    assert "neo4j-statefulset" not in lowered
    assert "kind: statefulset\nmetadata:\n  name: neo4j" not in lowered
    assert "neo4j_uri" in lowered
    assert "pcg_content_store_dsn" in lowered
    assert "pcg_postgres_dsn" in lowered


@pytest.mark.parametrize("compose_file", [COMPOSE_FILE, COMPOSE_TEMPLATE_FILE])
def test_compose_stack_includes_local_postgres_and_content_store_envs(
    compose_file: Path,
) -> None:
    data = yaml.safe_load(compose_file.read_text())
    services = data["services"]

    assert "postgres" in services
    assert "platform-context-graph" in services
    assert "neo4j" in services
    assert "repo-sync" in services

    postgres = services["postgres"]
    assert postgres["image"].startswith("postgres:")
    assert postgres["environment"]["POSTGRES_DB"] == "platform_context_graph"
    assert postgres["environment"]["POSTGRES_USER"] == "pcg"

    for service_name in ["bootstrap-index", "platform-context-graph", "repo-sync"]:
        envs = _compose_service_envs(services[service_name])
        assert envs["PCG_CONTENT_STORE_DSN"].startswith("postgresql://")
        assert envs["PCG_POSTGRES_DSN"].startswith("postgresql://")
        assert envs["PCG_REPOSITORY_RULES_JSON"] == "[]"


@pytest.mark.parametrize("compose_file", [COMPOSE_FILE, COMPOSE_TEMPLATE_FILE])
def test_compose_stack_includes_local_otel_collector_and_jaeger(
    compose_file: Path,
) -> None:
    data = yaml.safe_load(compose_file.read_text())
    services = data["services"]

    assert "otel-collector" in services
    assert "jaeger" in services

    collector = services["otel-collector"]
    jaeger = services["jaeger"]

    assert any(
        str(volume).endswith(
            "deploy/observability/otel-collector-config.yaml:"
            "/etc/otelcol-contrib/config.yaml:ro"
        )
        for volume in collector["volumes"]
    )
    assert jaeger["environment"]["COLLECTOR_OTLP_ENABLED"] == "true"

    for service_name in [
        "bootstrap-index",
        "platform-context-graph",
        "repo-sync",
    ]:
        envs = _compose_service_envs(services[service_name])
        assert envs["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-collector:4317"
        assert envs["OTEL_EXPORTER_OTLP_PROTOCOL"] == "grpc"
        assert envs["OTEL_EXPORTER_OTLP_INSECURE"] == "true"
        assert envs["OTEL_TRACES_EXPORTER"] == "otlp"
        assert envs["OTEL_METRICS_EXPORTER"] == "otlp"
        assert envs["OTEL_LOGS_EXPORTER"] == "none"

    assert OTEL_COLLECTOR_CONFIG_FILE.exists()
    collector_config = yaml.safe_load(OTEL_COLLECTOR_CONFIG_FILE.read_text())
    assert collector_config["receivers"]["otlp"]["protocols"]["grpc"]["endpoint"] == (
        "0.0.0.0:4317"
    )
    assert collector_config["exporters"]["otlp/jaeger"]["endpoint"] == (
        "jaeger:4317"
    )


def test_compose_stack_includes_service_and_external_test_database() -> None:
    data = yaml.safe_load(COMPOSE_FILE.read_text())
    services = data["services"]

    assert "platform-context-graph" in services
    assert "neo4j" in services
    assert "repo-sync" in services
    assert "postgres" in services
    assert services["repo-sync"]["command"] == ["pcg", "internal", "repo-sync-loop"]
    assert services["repo-sync"]["healthcheck"] == {"disable": True}


def test_chart_renders_otel_env_for_all_runtime_containers_when_enabled() -> None:
    docs = _render_chart(
        "--set",
        "observability.otel.enabled=true",
        "--set",
        "observability.otel.endpoint=otel-collector.monitoring.svc.cluster.local:4317",
        "--set",
        "observability.environment=ops-qa",
    )
    deployment = next(doc for doc in docs if doc["kind"] == "Deployment")
    statefulset = next(doc for doc in docs if doc["kind"] == "StatefulSet")
    pod_specs = [
        deployment["spec"]["template"]["spec"],
        statefulset["spec"]["template"]["spec"],
    ]

    expected_service_names = [
        "platform-context-graph-api",
        "platform-context-graph-ingester",
    ]

    for pod_spec, expected_service_name in zip(pod_specs, expected_service_names, strict=True):
        for container in [
            *pod_spec.get("initContainers", []),
            *pod_spec.get("containers", []),
        ]:
            env_by_name = {
                env["name"]: env.get("value", "")
                for env in container.get("env", [])
                if "name" in env
            }
            assert env_by_name["OTEL_EXPORTER_OTLP_ENDPOINT"].startswith(
                "otel-collector.monitoring.svc.cluster.local:4317"
            )
            assert env_by_name["OTEL_EXPORTER_OTLP_PROTOCOL"] == "grpc"
            assert env_by_name["OTEL_TRACES_EXPORTER"] == "otlp"
            assert env_by_name["OTEL_METRICS_EXPORTER"] == "otlp"
            assert env_by_name["OTEL_LOGS_EXPORTER"] == "none"
            assert env_by_name["OTEL_SERVICE_NAME"] == expected_service_name
            assert "OTEL_RESOURCE_ATTRIBUTES" in env_by_name


def test_chart_renders_content_store_envs_for_all_runtime_containers() -> None:
    docs = _render_chart(
        "--set",
        "contentStore.dsn=postgresql://pcg:replace-me@postgres.platform.svc.cluster.local:5432/platform_context_graph",
    )
    statefulset = next(doc for doc in docs if doc["kind"] == "StatefulSet")
    pod_spec = statefulset["spec"]["template"]["spec"]

    for container in [
        *pod_spec.get("initContainers", []),
        *pod_spec.get("containers", []),
    ]:
        env_by_name = {
            env["name"]: env.get("value", "")
            for env in container.get("env", [])
            if "name" in env
        }
        assert env_by_name["PCG_CONTENT_STORE_DSN"].startswith("postgresql://")
        assert env_by_name["PCG_POSTGRES_DSN"].startswith("postgresql://")


def test_argocd_base_values_include_external_content_store_and_repository_rules() -> (
    None
):
    values = yaml.safe_load((ARGOCD_BASE_DIR / "values.yaml").read_text())

    assert values["neo4j"]["uri"].startswith("bolt://")
    assert values["repoSync"]["source"]["rules"] == []
    assert values["contentStore"]["dsn"].startswith("postgresql://")
    assert values["env"]["PCG_LOG_FORMAT"] == "json"
    assert values["observability"]["otel"]["enabled"] is False
    assert values["observability"]["otel"]["protocol"] == "grpc"
    assert values["observability"]["otel"]["tracesExporter"] == "otlp"
    assert values["observability"]["otel"]["metricsExporter"] == "otlp"
    assert values["observability"]["otel"]["logsExporter"] == "none"


def test_product_dashboard_artifact_exists_and_is_valid_json() -> None:
    assert DASHBOARD_FILE.exists()
    dashboard = json.loads(DASHBOARD_FILE.read_text())
    assert dashboard["title"] == "PlatformContextGraph Observability"
    assert dashboard["panels"]


def test_compose_stack_supports_host_port_overrides() -> None:
    compose = shutil.which("docker-compose")
    if compose is None:
        pytest.skip("docker-compose is required for compose rendering tests")

    result = subprocess.run(
        [compose, "-f", str(COMPOSE_FILE), "config"],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "NEO4J_HTTP_PORT": "17474",
            "NEO4J_BOLT_PORT": "17687",
            "PCG_HTTP_PORT": "18080",
        },
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    rendered = yaml.safe_load(result.stdout)
    ports = rendered["services"]["neo4j"]["ports"]
    service_ports = rendered["services"]["platform-context-graph"]["ports"]

    assert {
        "published": "17474",
        "target": 7474,
        "protocol": "tcp",
        "mode": "ingress",
    } in ports
    assert {
        "published": "17687",
        "target": 7687,
        "protocol": "tcp",
        "mode": "ingress",
    } in ports
    assert {
        "published": "18080",
        "target": 8080,
        "protocol": "tcp",
        "mode": "ingress",
    } in service_ports


def test_compose_stack_supports_filesystem_host_root_override() -> None:
    compose = shutil.which("docker-compose")
    if compose is None:
        pytest.skip("docker-compose is required for compose rendering tests")

    result = subprocess.run(
        [compose, "-f", str(COMPOSE_FILE), "config"],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PCG_FILESYSTEM_HOST_ROOT": "/tmp/pcg-host-root",
        },
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    rendered = yaml.safe_load(result.stdout)

    for service_name in ["bootstrap-index", "repo-sync"]:
        volumes = rendered["services"][service_name]["volumes"]
        assert any(
            volume.get("type") == "bind"
            and volume.get("source") == "/tmp/pcg-host-root"
            and volume.get("target") == "/fixtures"
            and volume.get("read_only") is True
            for volume in volumes
        )


def test_checked_in_mcp_example_uses_compose_service_runtime() -> None:
    config = json.loads(MCP_EXAMPLE_FILE.read_text())
    server = config["mcpServers"]["pcg"]

    assert server["command"] == "sh"
    assert server["args"] == [
        "-lc",
        "cd <REPO_ROOT> && "
        "docker-compose exec -T platform-context-graph pcg mcp start",
    ]
    assert "env" not in server
