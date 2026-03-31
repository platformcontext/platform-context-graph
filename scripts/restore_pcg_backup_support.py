"""Config and cluster-discovery helpers for the PCG restore workflow."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Mapping, Sequence

BACKUP_DIR = Path.home() / "pcg-backups"
DEFAULT_NAMESPACE = "platformcontextgraph"
DEFAULT_VERIFY_TIMEOUT_SECONDS = 180


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments for the restore workflow."""

    parser = argparse.ArgumentParser(
        description=(
            "Restore Neo4j and PostgreSQL backups into a local "
            "docker compose stack."
        )
    )
    parser.add_argument("-p", "--postgres-dump", dest="pg_file")
    parser.add_argument("-n", "--neo4j-backup", dest="neo4j_file")
    parser.add_argument("--latest", action="store_true", dest="use_latest")
    parser.add_argument("--compose-file")
    parser.add_argument("--project-name")
    parser.add_argument("--fetch-auth-from-cluster", action="store_true")
    parser.add_argument("--verify-refinalize", action="store_true")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--api-port", type=int)
    parser.add_argument("--postgres-port", type=int)
    parser.add_argument("--neo4j-http-port", type=int)
    parser.add_argument("--neo4j-bolt-port", type=int)
    parser.add_argument("--jaeger-port", type=int)
    parser.add_argument("--otel-grpc-port", type=int)
    parser.add_argument("--otel-http-port", type=int)
    parser.add_argument("--otel-prometheus-port", type=int)
    parser.add_argument(
        "--verify-timeout-seconds",
        type=int,
        default=DEFAULT_VERIFY_TIMEOUT_SECONDS,
    )
    args = parser.parse_args(list(argv))
    if not args.pg_file and not args.neo4j_file:
        args.use_latest = True
    return args


def default_compose_file(project_root: Path) -> Path:
    """Return the preferred compose file for restore operations."""

    primary = project_root / "docker-compose.yaml"
    if primary.is_file():
        return primary
    template = project_root / "docker-compose.template.yml"
    if template.is_file():
        return template
    raise FileNotFoundError(
        "No docker-compose.yaml or docker-compose.template.yml found at "
        f"{project_root}"
    )


def compose_volume_name(project_name: str, volume_name: str) -> str:
    """Return the docker compose volume name for one project-local volume."""

    return f"{project_name}_{volume_name}"


def extract_neo4j_auth_secret_name(statefulset: Mapping[str, object]) -> str | None:
    """Read the mounted Neo4j auth secret from one StatefulSet document."""

    spec = statefulset.get("spec") or {}
    template = spec.get("template") or {}
    pod_spec = template.get("spec") or {}
    for volume in pod_spec.get("volumes") or []:
        if volume.get("name") != "neo4j-auth":
            continue
        secret = volume.get("secret") or {}
        name = str(secret.get("secretName") or "").strip()
        if name:
            return name
    return None


def select_neo4j_auth_secret(secret_names: Iterable[str]) -> str | None:
    """Pick the likeliest Neo4j auth secret from one fallback secret listing."""

    ordered = sorted(
        (str(name).strip() for name in secret_names if str(name).strip()),
        key=lambda value: (
            "neo4j-auth" not in value,
            "neo4j" not in value,
            "auth" not in value,
            value,
        ),
    )
    return ordered[0] if ordered else None


def compose_environment(
    *,
    api_port: int | None,
    postgres_port: int | None,
    neo4j_http_port: int | None,
    neo4j_bolt_port: int | None,
    jaeger_port: int | None,
    otel_grpc_port: int | None,
    otel_http_port: int | None,
    otel_prometheus_port: int | None,
    neo4j_password: str | None,
) -> dict[str, str]:
    """Build compose env overrides for restore and optional verification."""

    env = dict(os.environ)
    overrides = {
        "PCG_HTTP_PORT": api_port,
        "PCG_POSTGRES_PORT": postgres_port,
        "NEO4J_HTTP_PORT": neo4j_http_port,
        "NEO4J_BOLT_PORT": neo4j_bolt_port,
        "JAEGER_UI_PORT": jaeger_port,
        "OTEL_COLLECTOR_OTLP_GRPC_PORT": otel_grpc_port,
        "OTEL_COLLECTOR_OTLP_HTTP_PORT": otel_http_port,
        "OTEL_COLLECTOR_PROMETHEUS_PORT": otel_prometheus_port,
    }
    for key, value in overrides.items():
        if value is not None:
            env[key] = str(value)
    if neo4j_password:
        env["PCG_NEO4J_PASSWORD"] = neo4j_password
    return env


def fetch_cluster_neo4j_password(namespace: str) -> str:
    """Load the live Neo4j password from the active cluster."""

    secret_name = discover_neo4j_secret_name(namespace=namespace)
    secret_payload = json_output(
        ["kubectl", "get", "secret", "-n", namespace, secret_name, "-o", "json"]
    )
    encoded = str((secret_payload.get("data") or {}).get("password") or "").strip()
    if not encoded:
        raise RuntimeError(f"Secret {secret_name} is missing the password field")
    return base64.b64decode(encoded).decode("utf-8")


def discover_neo4j_secret_name(namespace: str) -> str:
    """Resolve the live Neo4j auth secret name from StatefulSets or secrets."""

    statefulsets = json_output(
        ["kubectl", "get", "statefulset", "-n", namespace, "-o", "json"]
    )
    for item in statefulsets.get("items") or []:
        secret_name = extract_neo4j_auth_secret_name(item)
        if secret_name:
            return secret_name
    secrets = json_output(["kubectl", "get", "secrets", "-n", namespace, "-o", "json"])
    secret_name = select_neo4j_auth_secret(
        item.get("metadata", {}).get("name", "") for item in secrets.get("items") or []
    )
    if secret_name:
        return secret_name
    raise RuntimeError("Could not discover the live Neo4j auth secret name")


def resolve_backup_files(args: argparse.Namespace) -> tuple[Path, Path]:
    """Pick explicit or latest backup files and validate that they exist."""

    pg_file = Path(args.pg_file).expanduser() if args.pg_file else None
    neo4j_file = Path(args.neo4j_file).expanduser() if args.neo4j_file else None
    if args.use_latest:
        if pg_file is None:
            pg_file = latest_matching_file("postgres-*.dump")
        if neo4j_file is None:
            neo4j_file = latest_matching_file("neo4j-*.tar.gz")
    if pg_file is None or not pg_file.is_file():
        raise FileNotFoundError(f"PostgreSQL dump not found: {pg_file}")
    if neo4j_file is None or not neo4j_file.is_file():
        raise FileNotFoundError(f"Neo4j backup not found: {neo4j_file}")
    return pg_file, neo4j_file


def latest_matching_file(pattern: str) -> Path:
    """Return the newest backup file matching one glob pattern."""

    candidates = sorted(BACKUP_DIR.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No backup files found for pattern {pattern} in {BACKUP_DIR}")
    return candidates[-1]


def pick_compose_command() -> list[str]:
    """Return the preferred docker compose command."""

    if shutil.which("docker"):
        probe = subprocess.run(
            ["docker", "compose", "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if probe.returncode == 0:
            return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    raise RuntimeError("Missing required compose command: docker compose or docker-compose")


def json_output(command: Sequence[str]) -> dict[str, object]:
    """Run one command and decode its JSON stdout payload."""

    completed = subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def print_backup_selection(*, pg_file: Path, neo4j_file: Path) -> None:
    """Emit a short backup selection summary for operators."""

    print(f"[i] PostgreSQL dump: {pg_file}")
    print(f"[i] Neo4j backup:    {neo4j_file}")
