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
DOCKERFILE = REPO_ROOT / "Dockerfile"
ENV_EXAMPLE_FILE = REPO_ROOT / ".env.example"
ROOT_PCGIGNORE = REPO_ROOT / ".pcgignore"
CHART_VALUES_FILE = CHART_DIR / "values.yaml"


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
    assert DOCKERFILE.exists()
    assert ENV_EXAMPLE_FILE.exists()
    assert ROOT_PCGIGNORE.exists()


def test_root_pcgignore_matches_chart_default_and_covers_generated_artifacts() -> None:
    """The checked-in `.pcgignore` should stay aligned with chart defaults."""

    root_text = ROOT_PCGIGNORE.read_text(encoding="utf-8").strip()
    chart_values = yaml.safe_load(CHART_VALUES_FILE.read_text(encoding="utf-8"))
    chart_text = str(chart_values["pcgignore"]).strip()

    assert root_text == chart_text
    for expected_pattern in (
        "*.min.js",
        "*.min.css",
        "*.min.map",
        ".dart_tool/",
        ".elixir_ls/",
        ".stack-work/",
        "CMakeFiles/",
        ".pnpm-store/",
    ):
        assert expected_pattern in root_text


def test_runtime_dockerfile_uses_non_root_data_home() -> None:
    dockerfile = DOCKERFILE.read_text()

    assert "useradd --create-home --uid 10001 --user-group pcg" in dockerfile
    assert "ENV HOME=/data" in dockerfile
    assert "ENV PCG_HOME=/data/.platform-context-graph" in dockerfile
    assert "USER pcg" in dockerfile
    assert "ENV PCG_HOME=/root/.platform-context-graph" not in dockerfile

    assert "go-builder" in dockerfile
    assert "pcg-ingester" in dockerfile
    assert "pcg-reducer" in dockerfile


def test_default_chart_renders_api_deployment_and_worker_statefulset() -> None:
    docs = _render_chart()
    kinds = _kinds(docs)

    assert "StatefulSet" in kinds
    assert "Deployment" in kinds
    assert "Service" in kinds
    assert "NetworkPolicy" in kinds
    assert "Ingress" not in kinds
    assert "HTTPRoute" not in kinds
    metadata_names = {doc.get("metadata", {}).get("name", "") for doc in docs}
    assert not any(name.endswith("neo4j") or name == "neo4j" for name in metadata_names)
    assert not any(name.endswith("-scripts") for name in metadata_names)

    api_deployment = next(
        doc
        for doc in docs
        if doc["kind"] == "Deployment"
        and doc["metadata"]["name"] == "platform-context-graph-api"
    )
    api_pod_spec = api_deployment["spec"]["template"]["spec"]
    api_container = next(
        container
        for container in api_pod_spec["containers"]
        if container["name"] == "platform-context-graph"
    )
    resolution_engine_deployment = next(
        doc
        for doc in docs
        if doc["kind"] == "Deployment"
        and doc["metadata"]["name"] == "platform-context-graph-resolution-engine"
    )
    resolution_engine_pod_spec = resolution_engine_deployment["spec"]["template"][
        "spec"
    ]
    resolution_engine_container = next(
        container
        for container in resolution_engine_pod_spec["containers"]
        if container["name"] == "resolution-engine"
    )

    worker_statefulset = next(doc for doc in docs if doc["kind"] == "StatefulSet")
    worker_pod_spec = worker_statefulset["spec"]["template"]["spec"]
    worker_container = next(
        container
        for container in worker_pod_spec["containers"]
        if container["name"] == "ingester"
    )
    worker_init_container = next(
        container
        for container in worker_pod_spec["initContainers"]
        if container["name"] == "workspace-setup"
    )

    assert worker_statefulset["metadata"]["name"] == "platform-context-graph"
    assert api_pod_spec.get("initContainers", []) == []
    assert api_container["command"] == [
        "pcg",
        "serve",
        "start",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
    ]
    assert resolution_engine_container["command"] == ["/usr/local/bin/pcg-reducer"]
    assert worker_container["command"] == ["/usr/local/bin/pcg-ingester"]
    assert worker_init_container["command"] == [
        "sh",
        "-c",
        "set -eu\nmkdir -p /data/repos\ncp /var/run/pcg-config/.pcgignore /data/repos/.pcgignore\nchown 10001:10001 /data /data/repos /data/repos/.pcgignore\n",
    ]
    assert (
        worker_statefulset["spec"]["serviceName"] == "platform-context-graph-ingester"
    )
    assert (
        worker_statefulset["spec"]["volumeClaimTemplates"][0]["metadata"]["name"]
        == "data"
    )
    assert api_deployment["spec"]["revisionHistoryLimit"] == 3
    assert resolution_engine_deployment["spec"]["revisionHistoryLimit"] == 3
    assert worker_statefulset["spec"]["revisionHistoryLimit"] == 3
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

    api_env_names = {env["name"] for env in api_container.get("env", [])}
    resolution_engine_env_items = {
        env["name"]: env
        for env in resolution_engine_container.get("env", [])
        if "name" in env
    }
    worker_env_names = {env["name"] for env in worker_container.get("env", [])}
    api_env_items = {
        env["name"]: env for env in api_container.get("env", []) if "name" in env
    }
    api_volume_mounts = {
        volume_mount["mountPath"]
        for volume_mount in api_container.get("volumeMounts", [])
    }
    resolution_engine_volume_mounts = {
        volume_mount["mountPath"]
        for volume_mount in resolution_engine_container.get("volumeMounts", [])
    }
    worker_volume_mounts = {
        volume_mount["mountPath"]
        for volume_mount in worker_container.get("volumeMounts", [])
    }
    worker_init_volume_mounts = {
        volume_mount["mountPath"]
        for volume_mount in worker_init_container.get("volumeMounts", [])
    }

    assert "PCG_REPOSITORY_RULES_JSON" not in api_env_names
    assert "PCG_REPOS_DIR" not in api_env_names
    assert api_env_items["PCG_RUNTIME_ROLE"]["value"] == "api"
    assert api_env_items["PCG_ENABLE_PUBLIC_DOCS"]["value"] == "false"
    assert api_env_items["LOG_FILE_PATH"]["value"] == ""
    assert (
        api_env_items["PCG_API_KEY"]["valueFrom"]["secretKeyRef"]["name"]
        == "pcg-api-auth"
    )
    assert api_env_items["PCG_API_KEY"]["valueFrom"]["secretKeyRef"]["key"] == "api-key"
    assert "PCG_REPOSITORY_RULES_JSON" in worker_env_names
    assert "PCG_REPOS_DIR" in worker_env_names
    assert "/data" not in api_volume_mounts
    assert (
        resolution_engine_env_items["PCG_RUNTIME_ROLE"]["value"] == "resolution-engine"
    )
    assert "PCG_API_KEY" not in resolution_engine_env_items
    assert "/data" not in resolution_engine_volume_mounts
    assert "/data" in worker_volume_mounts
    assert "/data/repos/.pcgignore" not in worker_volume_mounts
    assert worker_init_volume_mounts == {"/data", "/tmp", "/var/run/pcg-config"}


def test_default_chart_renders_runtime_security_contexts_and_tmp_mounts() -> None:
    docs = _render_chart()

    api_deployment = next(
        doc
        for doc in docs
        if doc["kind"] == "Deployment"
        and doc["metadata"]["name"] == "platform-context-graph-api"
    )
    api_pod_spec = api_deployment["spec"]["template"]["spec"]
    api_container = next(
        container
        for container in api_pod_spec["containers"]
        if container["name"] == "platform-context-graph"
    )
    resolution_engine_deployment = next(
        doc
        for doc in docs
        if doc["kind"] == "Deployment"
        and doc["metadata"]["name"] == "platform-context-graph-resolution-engine"
    )
    resolution_engine_pod_spec = resolution_engine_deployment["spec"]["template"][
        "spec"
    ]
    resolution_engine_container = next(
        container
        for container in resolution_engine_pod_spec["containers"]
        if container["name"] == "resolution-engine"
    )

    statefulset = next(doc for doc in docs if doc["kind"] == "StatefulSet")
    worker_pod_spec = statefulset["spec"]["template"]["spec"]
    worker_container = next(
        container
        for container in worker_pod_spec["containers"]
        if container["name"] == "ingester"
    )
    worker_init_container = next(
        container
        for container in worker_pod_spec["initContainers"]
        if container["name"] == "workspace-setup"
    )

    expected_pod_security = {
        "runAsNonRoot": True,
        "runAsUser": 10001,
        "runAsGroup": 10001,
        "fsGroup": 10001,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    expected_container_security = {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    expected_init_container_security = {
        "runAsNonRoot": False,
        "runAsUser": 0,
        "runAsGroup": 0,
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }

    assert api_pod_spec["securityContext"] == expected_pod_security
    assert resolution_engine_pod_spec["securityContext"] == expected_pod_security
    assert worker_pod_spec["securityContext"] == expected_pod_security
    assert api_container["securityContext"] == expected_container_security
    assert resolution_engine_container["securityContext"] == expected_container_security
    assert worker_container["securityContext"] == expected_container_security
    assert worker_init_container["securityContext"] == expected_init_container_security

    api_env = {
        env["name"]: env["value"]
        for env in api_container.get("env", [])
        if "name" in env and "value" in env
    }
    resolution_engine_env = {
        env["name"]: env["value"]
        for env in resolution_engine_container.get("env", [])
        if "name" in env and "value" in env
    }
    worker_env = {
        env["name"]: env["value"]
        for env in worker_container.get("env", [])
        if "name" in env and "value" in env
    }
    api_volume_mounts = {
        volume_mount["mountPath"]
        for volume_mount in api_container.get("volumeMounts", [])
    }
    resolution_engine_volume_mounts = {
        volume_mount["mountPath"]
        for volume_mount in resolution_engine_container.get("volumeMounts", [])
    }
    worker_volume_mounts = {
        volume_mount["mountPath"]
        for volume_mount in worker_container.get("volumeMounts", [])
    }
    api_volumes = {
        volume["name"]: volume
        for volume in api_pod_spec.get("volumes", [])
        if "name" in volume
    }
    resolution_engine_volumes = {
        volume["name"]: volume
        for volume in resolution_engine_pod_spec.get("volumes", [])
        if "name" in volume
    }
    worker_volumes = {
        volume["name"]: volume
        for volume in worker_pod_spec.get("volumes", [])
        if "name" in volume
    }

    assert api_env["PCG_HOME"] == "/tmp/.platform-context-graph"
    assert api_env["HOME"] == "/tmp"
    assert api_env["LOG_FILE_PATH"] == ""
    assert resolution_engine_env["PCG_HOME"] == "/tmp/.platform-context-graph"
    assert resolution_engine_env["HOME"] == "/tmp"
    assert resolution_engine_env["LOG_FILE_PATH"] == ""
    assert worker_env["HOME"] == "/data"
    assert worker_env["LOG_FILE_PATH"] == ""
    assert "/tmp" in api_volume_mounts
    assert "/tmp" in resolution_engine_volume_mounts
    assert "/tmp" in worker_volume_mounts
    assert api_volumes["tmp"]["emptyDir"] == {}
    assert resolution_engine_volumes["tmp"]["emptyDir"] == {}
    assert worker_volumes["tmp"]["emptyDir"] == {}


def test_default_chart_renders_network_policies_for_all_runtime_workloads() -> None:
    docs = _render_chart()
    policies = [doc for doc in docs if doc["kind"] == "NetworkPolicy"]

    assert len(policies) == 3

    api_policy = next(
        policy
        for policy in policies
        if policy["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/component"]
        == "api"
    )
    resolution_engine_policy = next(
        policy
        for policy in policies
        if policy["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/component"]
        == "resolution-engine"
    )
    ingester_policy = next(
        policy
        for policy in policies
        if policy["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/component"]
        == "ingester"
    )

    assert api_policy["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert api_policy["spec"]["ingress"] == [
        {"ports": [{"protocol": "TCP", "port": 8080}]}
    ]
    assert api_policy["spec"]["egress"] == [{}]

    assert resolution_engine_policy["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert resolution_engine_policy["spec"]["ingress"] == []
    assert resolution_engine_policy["spec"]["egress"] == [{}]

    assert ingester_policy["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert ingester_policy["spec"]["ingress"] == []
    assert ingester_policy["spec"]["egress"] == [{}]


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
    assert "ingester" in services
    assert "resolution-engine" in services

    postgres = services["postgres"]
    assert postgres["image"].startswith("postgres:")
    assert postgres["environment"]["POSTGRES_DB"] == "platform_context_graph"
    assert postgres["environment"]["POSTGRES_USER"] == "pcg"
    assert postgres["ports"] == ["${PCG_POSTGRES_PORT:-15432}:5432"]

    for service_name in [
        "bootstrap-index",
        "platform-context-graph",
        "ingester",
        "resolution-engine",
    ]:
        envs = _compose_service_envs(services[service_name])
        assert envs["PCG_CONTENT_STORE_DSN"].startswith("postgresql://")
        assert envs["PCG_POSTGRES_DSN"].startswith("postgresql://")
        assert envs["PCG_REPOSITORY_RULES_JSON"] == "[]"
        assert (
            envs["PCG_REPO_FILE_PARSE_MULTIPROCESS"]
            == "${PCG_REPO_FILE_PARSE_MULTIPROCESS:-false}"
        )
        assert envs["PCG_PARSE_WORKERS"] == "${PCG_PARSE_WORKERS:-4}"
        assert envs["PCG_WORKER_MAX_TASKS"] == "${PCG_WORKER_MAX_TASKS:-}"
        assert envs["PCG_INDEX_QUEUE_DEPTH"] == "${PCG_INDEX_QUEUE_DEPTH:-8}"

    service_envs = _compose_service_envs(services["platform-context-graph"])
    assert service_envs["PCG_RUNTIME_ROLE"] == "api"
    assert service_envs["PCG_AUTO_GENERATE_API_KEY"] == "true"
    resolution_engine_envs = _compose_service_envs(services["resolution-engine"])
    assert resolution_engine_envs["PCG_RUNTIME_ROLE"] == "resolution-engine"


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
    assert "${OTEL_COLLECTOR_PROMETHEUS_PORT:-9464}:9464" in collector["ports"]


@pytest.mark.parametrize("compose_file", [COMPOSE_FILE, COMPOSE_TEMPLATE_FILE])
def test_compose_stack_propagates_worker_tuning_envs(
    compose_file: Path,
) -> None:
    data = yaml.safe_load(compose_file.read_text())
    services = data["services"]

    for service_name in [
        "bootstrap-index",
        "platform-context-graph",
        "ingester",
        "resolution-engine",
    ]:
        envs = _compose_service_envs(services[service_name])
        assert "PCG_REPO_FILE_PARSE_MULTIPROCESS" in envs
        assert "PCG_PARSE_WORKERS" in envs
        assert "PCG_WORKER_MAX_TASKS" in envs
        assert "PCG_INDEX_QUEUE_DEPTH" in envs

    for service_name in [
        "bootstrap-index",
        "platform-context-graph",
        "ingester",
        "resolution-engine",
    ]:
        envs = _compose_service_envs(services[service_name])
        assert envs["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-collector:4317"
        assert envs["OTEL_EXPORTER_OTLP_PROTOCOL"] == "grpc"
        assert envs["OTEL_EXPORTER_OTLP_INSECURE"] == "true"
        assert envs["OTEL_TRACES_EXPORTER"] == "otlp"
        assert envs["OTEL_METRICS_EXPORTER"] == "otlp"
        assert envs["OTEL_LOGS_EXPORTER"] == "none"

    for service_name in [
        "platform-context-graph",
        "ingester",
        "resolution-engine",
    ]:
        envs = _compose_service_envs(services[service_name])
        assert envs["PCG_PROMETHEUS_METRICS_ENABLED"] == "true"
        assert envs["PCG_PROMETHEUS_METRICS_PORT"] == "9464"

    assert OTEL_COLLECTOR_CONFIG_FILE.exists()
    collector_config = yaml.safe_load(OTEL_COLLECTOR_CONFIG_FILE.read_text())
    assert collector_config["receivers"]["otlp"]["protocols"]["grpc"]["endpoint"] == (
        "0.0.0.0:4317"
    )
    assert collector_config["exporters"]["otlp/jaeger"]["endpoint"] == ("jaeger:4317")
    assert collector_config["exporters"]["prometheus"]["endpoint"] == "0.0.0.0:9464"
    assert collector_config["service"]["pipelines"]["metrics"]["receivers"] == ["otlp"]
    assert collector_config["service"]["pipelines"]["metrics"]["exporters"] == [
        "prometheus"
    ]


@pytest.mark.parametrize("compose_file", [COMPOSE_FILE, COMPOSE_TEMPLATE_FILE])
def test_compose_stack_exposes_runtime_metrics_ports(compose_file: Path) -> None:
    """Expose per-runtime Prometheus scrape ports for local verification."""

    data = yaml.safe_load(compose_file.read_text())
    services = data["services"]

    assert (
        "${PCG_API_METRICS_PORT:-19464}:9464"
        in services["platform-context-graph"]["ports"]
    )
    assert "${PCG_INGESTER_METRICS_PORT:-19465}:9464" in services["ingester"]["ports"]
    assert (
        "${PCG_RESOLUTION_ENGINE_METRICS_PORT:-19466}:9464"
        in services["resolution-engine"]["ports"]
    )


@pytest.mark.parametrize("compose_file", [COMPOSE_FILE, COMPOSE_TEMPLATE_FILE])
def test_compose_stack_parameterizes_local_passwords(compose_file: Path) -> None:
    rendered = compose_file.read_text()
    assert "testpassword" not in rendered

    data = yaml.safe_load(rendered)
    services = data["services"]

    assert _compose_service_envs(services["neo4j"])["NEO4J_AUTH"] == (
        "neo4j/${PCG_NEO4J_PASSWORD:-change-me}"
    )
    assert _compose_service_envs(services["postgres"])["POSTGRES_PASSWORD"] == (
        "${PCG_POSTGRES_PASSWORD:-change-me}"
    )

    for service_name in [
        "bootstrap-index",
        "platform-context-graph",
        "ingester",
        "resolution-engine",
    ]:
        envs = _compose_service_envs(services[service_name])
        assert envs["NEO4J_PASSWORD"] == "${PCG_NEO4J_PASSWORD:-change-me}"
        assert (
            envs["PCG_CONTENT_STORE_DSN"]
            == "postgresql://pcg:${PCG_POSTGRES_PASSWORD:-change-me}@postgres:5432/platform_context_graph"
        )
        assert (
            envs["PCG_POSTGRES_DSN"]
            == "postgresql://pcg:${PCG_POSTGRES_PASSWORD:-change-me}@postgres:5432/platform_context_graph"
        )


def test_env_example_documents_local_compose_secret_placeholders() -> None:
    env_example = ENV_EXAMPLE_FILE.read_text()

    assert "PCG_NEO4J_PASSWORD=" in env_example
    assert "PCG_POSTGRES_PASSWORD=" in env_example
    assert "PCG_API_KEY=" in env_example


def test_compose_stack_includes_service_and_external_test_database() -> None:
    data = yaml.safe_load(COMPOSE_FILE.read_text())
    services = data["services"]

    assert "platform-context-graph" in services
    assert "neo4j" in services
    assert "ingester" in services
    assert "resolution-engine" in services
    assert "postgres" in services
    ingester_service = services["ingester"]
    assert "entrypoint" in ingester_service
    assert "exec /usr/local/bin/pcg-ingester" in "\n".join(
        ingester_service["entrypoint"]
    )
    assert services["ingester"]["healthcheck"] == {"disable": True}
    assert services["resolution-engine"]["command"] == ["/usr/local/bin/pcg-reducer"]
    assert services["resolution-engine"]["healthcheck"] == {"disable": True}


def test_chart_renders_otel_env_for_all_runtime_containers_when_enabled() -> None:
    docs = _render_chart(
        "--set",
        "observability.otel.enabled=true",
        "--set",
        "observability.otel.endpoint=otel-collector.monitoring.svc.cluster.local:4317",
        "--set",
        "observability.environment=ops-qa",
    )
    api_deployment = next(
        doc
        for doc in docs
        if doc["kind"] == "Deployment"
        and doc["metadata"]["name"] == "platform-context-graph-api"
    )
    resolution_engine_deployment = next(
        doc
        for doc in docs
        if doc["kind"] == "Deployment"
        and doc["metadata"]["name"] == "platform-context-graph-resolution-engine"
    )
    statefulset = next(doc for doc in docs if doc["kind"] == "StatefulSet")
    pod_specs = [
        api_deployment["spec"]["template"]["spec"],
        resolution_engine_deployment["spec"]["template"]["spec"],
        statefulset["spec"]["template"]["spec"],
    ]

    expected_service_names = [
        "platform-context-graph-api",
        "platform-context-graph-resolution-engine",
        "platform-context-graph-ingester",
    ]

    for pod_spec, expected_service_name in zip(
        pod_specs, expected_service_names, strict=True
    ):
        for container in pod_spec.get("containers", []):
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


def test_chart_renders_prometheus_metrics_services_and_service_monitors() -> None:
    """Render per-runtime metrics services and service monitors when enabled."""

    docs = _render_chart(
        "--set",
        "observability.prometheus.enabled=true",
        "--set",
        "observability.prometheus.serviceMonitor.enabled=true",
        "--set",
        "observability.prometheus.port=9464",
    )

    services = {
        doc["metadata"]["name"]: doc for doc in docs if doc["kind"] == "Service"
    }
    service_monitors = {
        doc["metadata"]["name"]: doc for doc in docs if doc["kind"] == "ServiceMonitor"
    }
    expected_metrics_names = [
        "platform-context-graph-api-metrics",
        "platform-context-graph-ingester-metrics",
        "platform-context-graph-resolution-engine-metrics",
    ]

    for name in expected_metrics_names:
        assert name in services
        assert name in service_monitors
        endpoint = service_monitors[name]["spec"]["endpoints"][0]
        assert endpoint["port"] == "metrics"
        assert endpoint["path"] == "/metrics"

    api_deployment = next(
        doc
        for doc in docs
        if doc["kind"] == "Deployment"
        and doc["metadata"]["name"] == "platform-context-graph-api"
    )
    resolution_engine_deployment = next(
        doc
        for doc in docs
        if doc["kind"] == "Deployment"
        and doc["metadata"]["name"] == "platform-context-graph-resolution-engine"
    )
    ingester_statefulset = next(doc for doc in docs if doc["kind"] == "StatefulSet")

    for pod_spec in [
        api_deployment["spec"]["template"]["spec"],
        resolution_engine_deployment["spec"]["template"]["spec"],
        ingester_statefulset["spec"]["template"]["spec"],
    ]:
        container = pod_spec["containers"][0]
        ports = {port["name"]: port["containerPort"] for port in container["ports"]}
        env_by_name = {
            env["name"]: env.get("value", "")
            for env in container.get("env", [])
            if "name" in env
        }
        assert ports["metrics"] == 9464
        assert env_by_name["PCG_PROMETHEUS_METRICS_ENABLED"] == "true"
        assert env_by_name["PCG_PROMETHEUS_METRICS_PORT"] == "9464"


def test_chart_renders_content_store_envs_for_all_runtime_containers() -> None:
    docs = _render_chart(
        "--set",
        "contentStore.dsn=postgresql://pcg:replace-me@postgres.platform.svc.cluster.local:5432/platform_context_graph",
    )
    statefulset = next(doc for doc in docs if doc["kind"] == "StatefulSet")
    pod_spec = statefulset["spec"]["template"]["spec"]

    for container in pod_spec.get("containers", []):
        env_by_name = {
            env["name"]: env.get("value", "")
            for env in container.get("env", [])
            if "name" in env
        }
        assert env_by_name["PCG_CONTENT_STORE_DSN"].startswith("postgresql://")
        assert env_by_name["PCG_POSTGRES_DSN"].startswith("postgresql://")


def test_chart_renders_component_scoped_connection_tuning_envs() -> None:
    docs = _render_chart(
        "--set-string",
        "api.connectionTuning.postgres.maxOpenConns=31",
        "--set-string",
        "api.connectionTuning.neo4j.maxConnectionPoolSize=45",
        "--set-string",
        "resolutionEngine.connectionTuning.postgres.connMaxIdleTime=7m",
        "--set-string",
        "resolutionEngine.connectionTuning.neo4j.verifyTimeout=11s",
        "--set-string",
        "ingester.connectionTuning.postgres.pingTimeout=9s",
        "--set-string",
        "ingester.connectionTuning.neo4j.connectionAcquisitionTimeout=15s",
    )
    api_deployment = next(
        doc
        for doc in docs
        if doc["kind"] == "Deployment"
        and doc["metadata"]["name"] == "platform-context-graph-api"
    )
    resolution_engine_deployment = next(
        doc
        for doc in docs
        if doc["kind"] == "Deployment"
        and doc["metadata"]["name"] == "platform-context-graph-resolution-engine"
    )
    ingester_statefulset = next(doc for doc in docs if doc["kind"] == "StatefulSet")

    api_env_by_name = {
        env["name"]: env.get("value", "")
        for env in api_deployment["spec"]["template"]["spec"]["containers"][0]["env"]
        if "name" in env
    }
    resolution_engine_env_by_name = {
        env["name"]: env.get("value", "")
        for env in resolution_engine_deployment["spec"]["template"]["spec"][
            "containers"
        ][0]["env"]
        if "name" in env
    }
    ingester_env_by_name = {
        env["name"]: env.get("value", "")
        for env in ingester_statefulset["spec"]["template"]["spec"]["containers"][0][
            "env"
        ]
        if "name" in env
    }

    assert api_env_by_name["PCG_POSTGRES_MAX_OPEN_CONNS"] == "31"
    assert api_env_by_name["PCG_NEO4J_MAX_CONNECTION_POOL_SIZE"] == "45"
    assert "PCG_POSTGRES_CONN_MAX_IDLE_TIME" not in api_env_by_name

    assert resolution_engine_env_by_name["PCG_POSTGRES_CONN_MAX_IDLE_TIME"] == "7m"
    assert resolution_engine_env_by_name["PCG_NEO4J_VERIFY_TIMEOUT"] == "11s"
    assert "PCG_POSTGRES_MAX_OPEN_CONNS" not in resolution_engine_env_by_name

    assert ingester_env_by_name["PCG_POSTGRES_PING_TIMEOUT"] == "9s"
    assert ingester_env_by_name["PCG_NEO4J_CONNECTION_ACQUISITION_TIMEOUT"] == "15s"
    assert "PCG_NEO4J_VERIFY_TIMEOUT" not in ingester_env_by_name


def test_minimal_manifest_exposes_connection_tuning_defaults() -> None:
    configmap = (MINIMAL_MANIFEST_DIR / "configmap.yaml").read_text()

    assert "PCG_POSTGRES_MAX_OPEN_CONNS" in configmap
    assert "PCG_POSTGRES_CONN_MAX_IDLE_TIME" in configmap
    assert "PCG_NEO4J_MAX_CONNECTION_POOL_SIZE" in configmap
    assert "PCG_NEO4J_VERIFY_TIMEOUT" in configmap


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
            "PCG_POSTGRES_PORT": "15433",
            "PCG_HTTP_PORT": "18080",
        },
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    rendered = yaml.safe_load(result.stdout)
    ports = rendered["services"]["neo4j"]["ports"]
    service_ports = rendered["services"]["platform-context-graph"]["ports"]
    postgres_ports = rendered["services"]["postgres"]["ports"]

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
    assert {
        "published": "15433",
        "target": 5432,
        "protocol": "tcp",
        "mode": "ingress",
    } in postgres_ports


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

    for service_name in ["bootstrap-index", "ingester", "resolution-engine"]:
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
        "cd <REPO_ROOT> && docker-compose exec -T platform-context-graph pcg mcp start",
    ]
    assert "env" not in server
