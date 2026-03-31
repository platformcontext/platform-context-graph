"""Unit tests for the PCG restore tooling."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "restore_pcg_backup.py"


def _load_module(module_name: str) -> ModuleType:
    """Load the restore script module under one isolated test name."""

    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.path.insert(0, str(REPO_ROOT))
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_default_compose_file_prefers_primary_yaml(tmp_path: Path) -> None:
    """The restore flow should prefer the main compose file when both exist."""

    module = _load_module("restore_pcg_backup_primary_compose_test")
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "docker-compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (project_root / "docker-compose.template.yml").write_text(
        "services: {}\n",
        encoding="utf-8",
    )

    assert module.default_compose_file(project_root) == (
        project_root / "docker-compose.yaml"
    )


def test_compose_volume_name_uses_project_name_prefix() -> None:
    """Derived compose volumes should honor the selected project name."""

    module = _load_module("restore_pcg_backup_volume_name_test")

    assert module.compose_volume_name("pcg-restoretest", "neo4j_data") == (
        "pcg-restoretest_neo4j_data"
    )


def test_extract_neo4j_auth_secret_name_from_statefulset() -> None:
    """Neo4j auth discovery should read the mounted auth secret name."""

    module = _load_module("restore_pcg_backup_secret_name_test")
    statefulset = {
        "spec": {
            "template": {
                "spec": {
                    "volumes": [
                        {
                            "name": "neo4j-auth",
                            "secret": {"secretName": "platformcontextgraph-neo4j-auth"},
                        }
                    ]
                }
            }
        }
    }

    assert module.extract_neo4j_auth_secret_name(statefulset) == (
        "platformcontextgraph-neo4j-auth"
    )


def test_select_neo4j_auth_secret_prefers_exact_auth_match() -> None:
    """Fallback secret selection should prefer the auth secret over other hits."""

    module = _load_module("restore_pcg_backup_secret_select_test")

    assert module.select_neo4j_auth_secret(
        [
            "platformcontextgraph-api-auth",
            "platformcontextgraph-neo4j-auth",
            "platformcontextgraph-postgresql-auth",
        ]
    ) == "platformcontextgraph-neo4j-auth"


def test_parse_args_enables_cluster_auth_and_verification() -> None:
    """The new restore flags should parse into one coherent options object."""

    module = _load_module("restore_pcg_backup_parse_args_test")

    args = module.parse_args(
        [
            "--latest",
            "--project-name",
            "pcg-restoretest",
            "--fetch-auth-from-cluster",
            "--verify-refinalize",
            "--api-port",
            "18180",
            "--postgres-port",
            "25440",
            "--neo4j-http-port",
            "17490",
            "--neo4j-bolt-port",
            "17690",
        ]
    )

    assert args.use_latest is True
    assert args.project_name == "pcg-restoretest"
    assert args.fetch_auth_from_cluster is True
    assert args.verify_refinalize is True
    assert args.api_port == 18180
    assert args.postgres_port == 25440
    assert args.neo4j_http_port == 17490
    assert args.neo4j_bolt_port == 17690


def test_run_refinalize_verification_invokes_pytest_with_compose_api_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verification should invoke the existing compose pytest with live API env."""

    module = _load_module("restore_pcg_backup_verify_test")
    captured: dict[str, object] = {}

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        Path(env["PCG_E2E_RUN_ID_FILE"]).write_text("refinalize-api-test", encoding="utf-8")
        Path(env["PCG_E2E_STATUS_FILE"]).write_text("{}", encoding="utf-8")

    monkeypatch.setattr(module, "_run_checked", fake_run)

    result = module.run_refinalize_verification(
        repo_root=REPO_ROOT,
        api_base_url="http://localhost:18180/api/v0",
        api_key="secret-key",
        timeout_seconds=900,
        artifact_dir=tmp_path,
    )

    assert captured["command"] == [
        "uv",
        "run",
        "pytest",
        "tests/e2e/test_admin_refinalize_compose.py",
        "-q",
    ]
    assert captured["cwd"] == REPO_ROOT
    env = captured["env"]
    assert env["PCG_E2E_API_BASE_URL"] == "http://localhost:18180/api/v0"
    assert env["PCG_E2E_API_KEY"] == "secret-key"
    assert env["PCG_E2E_TIMEOUT_SECONDS"] == "900"
    assert env["PYTHONPATH"] == "src"
    assert result.run_id == "refinalize-api-test"
    assert Path(result.run_id_file).is_file()
    assert Path(result.status_file).is_file()


def test_compose_environment_overrides_include_selected_ports() -> None:
    """Compose env exports should include the caller-selected host ports."""

    module = _load_module("restore_pcg_backup_compose_env_test")

    env = module.compose_environment(
        api_port=18180,
        postgres_port=25440,
        neo4j_http_port=17490,
        neo4j_bolt_port=17690,
        jaeger_port=26690,
        otel_grpc_port=24330,
        otel_http_port=24331,
        otel_prometheus_port=29480,
        neo4j_password="cluster-secret",
    )

    assert env["PCG_HTTP_PORT"] == "18180"
    assert env["PCG_POSTGRES_PORT"] == "25440"
    assert env["NEO4J_HTTP_PORT"] == "17490"
    assert env["NEO4J_BOLT_PORT"] == "17690"
    assert env["JAEGER_UI_PORT"] == "26690"
    assert env["OTEL_COLLECTOR_OTLP_GRPC_PORT"] == "24330"
    assert env["OTEL_COLLECTOR_OTLP_HTTP_PORT"] == "24331"
    assert env["OTEL_COLLECTOR_PROMETHEUS_PORT"] == "29480"
    assert env["PCG_NEO4J_PASSWORD"] == "cluster-secret"
    assert env["PATH"] == os.environ["PATH"]


def test_restore_database_services_waits_for_neo4j_after_data_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Database restore should re-wait for Neo4j health after the store swap."""

    module = _load_module("restore_pcg_backup_restore_order_test")
    events: list[tuple[str, str]] = []

    def fake_compose_output(*_args, **kwargs) -> str:
        service = kwargs["args"][-1]
        return f"{service}-container"

    monkeypatch.setattr(module, "compose_output", fake_compose_output)
    monkeypatch.setattr(
        module,
        "wait_for_container_health",
        lambda container_id, **_kwargs: events.append(("wait", container_id)),
    )
    monkeypatch.setattr(
        module,
        "restore_postgres",
        lambda **_kwargs: events.append(("restore_postgres", "postgres-container")),
    )
    monkeypatch.setattr(
        module,
        "restore_neo4j",
        lambda **_kwargs: events.append(("restore_neo4j", "neo4j-container")),
    )

    pg_container, neo4j_container = module._restore_database_services(
        compose_cmd=["docker", "compose"],
        compose_file=REPO_ROOT / "docker-compose.yaml",
        project_name="pcg-restoretest",
        env={},
        cwd=REPO_ROOT,
        pg_file=Path("/tmp/postgres.dump"),
        neo4j_file=Path("/tmp/neo4j.tar.gz"),
    )

    assert (pg_container, neo4j_container) == ("postgres-container", "neo4j-container")
    assert events == [
        ("wait", "postgres-container"),
        ("wait", "neo4j-container"),
        ("restore_postgres", "postgres-container"),
        ("restore_neo4j", "neo4j-container"),
        ("wait", "neo4j-container"),
    ]
