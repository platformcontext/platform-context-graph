"""Runtime helpers for the PCG backup restore workflow."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Mapping, Sequence
from urllib.error import URLError
from urllib.request import urlopen


def compose(
    compose_cmd: Sequence[str],
    *,
    compose_file: Path,
    project_name: str,
    args: Sequence[str],
    env: Mapping[str, str],
    cwd: Path,
) -> None:
    """Run one compose command with the selected file and project name."""

    run_checked(
        [*compose_cmd, "-f", str(compose_file), "-p", project_name, *args],
        cwd=cwd,
        env=env,
    )


def compose_output(
    compose_cmd: Sequence[str],
    *,
    compose_file: Path,
    project_name: str,
    args: Sequence[str],
    env: Mapping[str, str],
    cwd: Path,
) -> str:
    """Capture stdout for one compose subcommand."""

    return capture_text(
        [*compose_cmd, "-f", str(compose_file), "-p", project_name, *args],
        cwd=cwd,
        env=env,
    ).strip()


def restore_postgres(*, pg_container: str, pg_file: Path, cwd: Path) -> None:
    """Replace the local PostgreSQL database with the backup contents."""

    commands = [
        (
            [
                "docker",
                "exec",
                "-i",
                pg_container,
                "psql",
                "-U",
                "pcg",
                "-d",
                "postgres",
                "-c",
                (
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = 'platform_context_graph' "
                    "AND pid <> pg_backend_pid();"
                ),
            ],
            False,
        ),
        (
            [
                "docker",
                "exec",
                "-i",
                pg_container,
                "psql",
                "-U",
                "pcg",
                "-d",
                "postgres",
                "-c",
                "DROP DATABASE IF EXISTS platform_context_graph;",
            ],
            True,
        ),
        (
            [
                "docker",
                "exec",
                "-i",
                pg_container,
                "psql",
                "-U",
                "pcg",
                "-d",
                "postgres",
                "-c",
                "CREATE DATABASE platform_context_graph OWNER pcg;",
            ],
            True,
        ),
    ]
    env = os.environ.copy()
    for command, required in commands:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if required and completed.returncode != 0:
            raise subprocess.CalledProcessError(completed.returncode, command)
    with pg_file.open("rb") as dump_handle:
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                pg_container,
                "pg_restore",
                "--no-owner",
                "--role=pcg",
                "-U",
                "pcg",
                "-d",
                "platform_context_graph",
            ],
            cwd=cwd,
            env=env,
            stdin=dump_handle,
            check=True,
        )


def restore_neo4j(
    *,
    neo4j_container: str,
    neo4j_file: Path,
    volume_name: str,
    cwd: Path,
) -> None:
    """Replace the compose Neo4j data volume with the backup tarball."""

    env = os.environ.copy()
    subprocess.run(
        ["docker", "stop", neo4j_container],
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    run_checked(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume_name}:/data",
            "alpine",
            "sh",
            "-c",
            "rm -rf /data/databases /data/transactions",
        ],
        cwd=cwd,
        env=env,
    )
    run_checked(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume_name}:/data",
            "-v",
            f"{neo4j_file}:/backup.tar.gz",
            "alpine",
            "sh",
            "-c",
            (
                "tar xzf /backup.tar.gz -C /data/ && "
                "chown -R 7474:7474 /data/databases /data/transactions"
            ),
        ],
        cwd=cwd,
        env=env,
    )
    run_checked(["docker", "start", neo4j_container], cwd=cwd, env=env)


def wait_for_container_health(
    container_id: str, *, cwd: Path, timeout_seconds: int = 120
) -> None:
    """Wait until one docker container reports healthy or exits."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = capture_text(
            ["docker", "inspect", "-f", "{{json .State.Health}}", container_id],
            cwd=cwd,
            env=os.environ.copy(),
        ).strip()
        if '"Status":"healthy"' in state:
            return
        if '"Status":"unhealthy"' in state:
            raise RuntimeError(f"Container {container_id} became unhealthy")
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for container {container_id} to become healthy")


def wait_for_http(url: str, *, timeout_seconds: int = 120) -> None:
    """Wait until one HTTP endpoint returns a successful response."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=5) as response:
                if 200 <= response.status < 300:
                    return
        except URLError:
            pass
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for {url}")


def read_api_key(*, api_container: str, cwd: Path) -> str:
    """Read the generated API key from the running compose API container."""

    api_key = capture_text(
        [
            "docker",
            "exec",
            api_container,
            "sh",
            "-lc",
            "grep '^PCG_API_KEY=' /data/.platform-context-graph/.env | cut -d= -f2-",
        ],
        cwd=cwd,
        env=os.environ.copy(),
    ).strip()
    if not api_key:
        raise RuntimeError("Could not read the generated compose API key")
    return api_key


def neo4j_query_scalar(
    *, neo4j_container: str, password: str, query: str, cwd: Path
) -> str:
    """Run one Cypher query inside the compose Neo4j container and return the scalar."""

    output = capture_text(
        [
            "docker",
            "exec",
            neo4j_container,
            "cypher-shell",
            "-u",
            "neo4j",
            "-p",
            password,
            query,
        ],
        cwd=cwd,
        env=os.environ.copy(),
    )
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else "?"


def postgres_query_scalar(*, pg_container: str, query: str, cwd: Path) -> str:
    """Run one SQL scalar query inside the compose PostgreSQL container."""

    return capture_text(
        [
            "docker",
            "exec",
            "-i",
            pg_container,
            "psql",
            "-U",
            "pcg",
            "-d",
            "platform_context_graph",
            "-At",
            "-c",
            query,
        ],
        cwd=cwd,
        env=os.environ.copy(),
    ).strip()


def capture_text(command: Sequence[str], *, cwd: Path, env: Mapping[str, str]) -> str:
    """Run one command and return stdout as text."""

    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(env),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def run_checked(command: Sequence[str], *, cwd: Path, env: Mapping[str, str]) -> None:
    """Run one command and raise on failure."""

    subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(env),
        check=True,
    )
