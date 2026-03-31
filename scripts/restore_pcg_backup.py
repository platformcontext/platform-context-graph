"""Restore PCG PostgreSQL and Neo4j backups into a local compose stack."""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.restore_pcg_backup_runtime import (
    compose,
    compose_output,
    neo4j_query_scalar,
    postgres_query_scalar,
    read_api_key,
    restore_neo4j,
    restore_postgres,
    run_checked as _support_run_checked,
    wait_for_container_health,
    wait_for_http,
)
from scripts.restore_pcg_backup_support import (
    DEFAULT_NAMESPACE,
    compose_environment,
    compose_volume_name,
    default_compose_file,
    extract_neo4j_auth_secret_name,
    fetch_cluster_neo4j_password,
    parse_args,
    pick_compose_command,
    print_backup_selection,
    resolve_backup_files,
    select_neo4j_auth_secret,
)


@dataclass(frozen=True)
class VerificationArtifacts:
    """Paths and metadata emitted by the refinalize verification step."""

    run_id: str
    run_id_file: Path
    status_file: Path


def run_refinalize_verification(
    *,
    repo_root: Path,
    api_base_url: str,
    api_key: str,
    timeout_seconds: int,
    artifact_dir: Path,
) -> VerificationArtifacts:
    """Run the compose-backed admin refinalize pytest against one live stack."""

    run_id_file = artifact_dir / "run_id.txt"
    status_file = artifact_dir / "status.json"
    env = dict(os.environ)
    env.update(
        {
            "PCG_E2E_API_BASE_URL": api_base_url,
            "PCG_E2E_API_KEY": api_key,
            "PCG_E2E_TIMEOUT_SECONDS": str(timeout_seconds),
            "PCG_E2E_RUN_ID_FILE": str(run_id_file),
            "PCG_E2E_STATUS_FILE": str(status_file),
            "PYTHONPATH": "src",
        }
    )
    _run_checked(
        [
            "uv",
            "run",
            "pytest",
            "tests/e2e/test_admin_refinalize_compose.py",
            "-q",
        ],
        cwd=repo_root,
        env=env,
    )
    run_id = run_id_file.read_text(encoding="utf-8").strip()
    return VerificationArtifacts(
        run_id=run_id,
        run_id_file=run_id_file,
        status_file=status_file,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the restore workflow."""

    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = REPO_ROOT
    compose_file = (
        Path(args.compose_file).resolve()
        if args.compose_file
        else default_compose_file(repo_root)
    )
    project_name = args.project_name or os.environ.get("COMPOSE_PROJECT_NAME")
    if not project_name:
        project_name = repo_root.name

    compose_cmd = pick_compose_command()
    pg_file, neo4j_file = resolve_backup_files(args)
    print_backup_selection(pg_file=pg_file, neo4j_file=neo4j_file)

    neo4j_password = os.environ.get("PCG_NEO4J_PASSWORD") or "change-me"
    if args.fetch_auth_from_cluster:
        neo4j_password = fetch_cluster_neo4j_password(
            namespace=args.namespace or DEFAULT_NAMESPACE
        )

    env = compose_environment(
        api_port=args.api_port,
        postgres_port=args.postgres_port,
        neo4j_http_port=args.neo4j_http_port,
        neo4j_bolt_port=args.neo4j_bolt_port,
        jaeger_port=args.jaeger_port,
        otel_grpc_port=args.otel_grpc_port,
        otel_http_port=args.otel_http_port,
        otel_prometheus_port=args.otel_prometheus_port,
        neo4j_password=neo4j_password,
    )

    services = ["neo4j", "postgres"]
    if args.verify_refinalize:
        services.extend(["jaeger", "otel-collector"])
    compose(
        compose_cmd,
        compose_file=compose_file,
        project_name=project_name,
        args=["up", "-d", *services],
        env=env,
        cwd=repo_root,
    )

    pg_container, neo4j_container = _restore_database_services(
        compose_cmd=compose_cmd,
        compose_file=compose_file,
        project_name=project_name,
        env=env,
        cwd=repo_root,
        pg_file=pg_file,
        neo4j_file=neo4j_file,
    )

    repo_count = neo4j_query_scalar(
        neo4j_container=neo4j_container,
        password=neo4j_password,
        query="MATCH (r:Repository) RETURN count(r) AS count",
        cwd=repo_root,
    )
    print(f"[+] Neo4j restore complete. Repositories in graph: {repo_count}")

    pg_table_count = postgres_query_scalar(
        pg_container=pg_container,
        query=(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public';"
        ),
        cwd=repo_root,
    )
    print(f"[i] PostgreSQL tables: {pg_table_count}")

    if args.verify_refinalize:
        verification = _verify_restored_stack(
            compose_cmd=compose_cmd,
            compose_file=compose_file,
            project_name=project_name,
            env=env,
            cwd=repo_root,
            timeout_seconds=args.verify_timeout_seconds,
        )
        print(f"[+] Admin refinalize verification passed. run_id: {verification.run_id}")

    print("[+] Restore complete.")
    return 0


def _restore_database_services(
    *,
    compose_cmd: Sequence[str],
    compose_file: Path,
    project_name: str,
    env: Mapping[str, str],
    cwd: Path,
    pg_file: Path,
    neo4j_file: Path,
) -> tuple[str, str]:
    """Wait for base services, then restore both databases from backup."""

    pg_container = compose_output(
        compose_cmd,
        compose_file=compose_file,
        project_name=project_name,
        args=["ps", "-q", "postgres"],
        env=env,
        cwd=cwd,
    ).strip()
    neo4j_container = compose_output(
        compose_cmd,
        compose_file=compose_file,
        project_name=project_name,
        args=["ps", "-q", "neo4j"],
        env=env,
        cwd=cwd,
    ).strip()
    if not pg_container or not neo4j_container:
        raise RuntimeError("Could not resolve postgres/neo4j compose containers")
    wait_for_container_health(pg_container, cwd=cwd)
    wait_for_container_health(neo4j_container, cwd=cwd)
    restore_postgres(pg_container=pg_container, pg_file=pg_file, cwd=cwd)
    restore_neo4j(
        neo4j_container=neo4j_container,
        neo4j_file=neo4j_file,
        volume_name=compose_volume_name(project_name, "neo4j_data"),
        cwd=cwd,
    )
    wait_for_container_health(neo4j_container, cwd=cwd)
    return pg_container, neo4j_container


def _verify_restored_stack(
    *,
    compose_cmd: Sequence[str],
    compose_file: Path,
    project_name: str,
    env: Mapping[str, str],
    cwd: Path,
    timeout_seconds: int,
) -> VerificationArtifacts:
    """Start the API service against restored data and run the E2E smoke test."""

    compose(
        compose_cmd,
        compose_file=compose_file,
        project_name=project_name,
        args=["up", "-d", "--no-deps", "platform-context-graph"],
        env=env,
        cwd=cwd,
    )
    api_port = int(env.get("PCG_HTTP_PORT", "8080"))
    wait_for_http(f"http://localhost:{api_port}/health")
    api_container = compose_output(
        compose_cmd,
        compose_file=compose_file,
        project_name=project_name,
        args=["ps", "-q", "platform-context-graph"],
        env=env,
        cwd=cwd,
    ).strip()
    api_key = read_api_key(api_container=api_container, cwd=cwd)
    with tempfile.TemporaryDirectory() as temp_dir:
        return run_refinalize_verification(
            repo_root=cwd,
            api_base_url=f"http://localhost:{api_port}/api/v0",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            artifact_dir=Path(temp_dir),
        )


def _run_checked(
    command: Sequence[str], *, cwd: Path, env: Mapping[str, str]
) -> None:
    """Run one command and raise on failure."""

    _support_run_checked(command, cwd=cwd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
