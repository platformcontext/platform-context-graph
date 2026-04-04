"""Public CLI entrypoint assembly for PlatformContextGraph."""

from __future__ import annotations

import json
import logging
import os
import sys
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

import typer
from dotenv import find_dotenv
from rich.console import Console

from platform_context_graph.core.database import DatabaseManager  # noqa: F401
from platform_context_graph.runtime.ingester import (
    RepoSyncConfig,  # noqa: F401
    run_bootstrap_index,  # noqa: F401
    run_repo_sync_cycle,  # noqa: F401
    run_repo_sync_loop,  # noqa: F401
)
from platform_context_graph.mcp import MCPServer
from platform_context_graph.observability import configure_logging
from platform_context_graph.versioning import ensure_v_prefix

from ..paths import get_app_env_file
from . import config_manager
from .commands.analyze_graph import register_analyze_graph_commands
from .commands.analyze_quality import register_analyze_quality_commands
from .commands.basic import register_basic_commands
from .commands.bundle_registry import register_bundle_registry_commands
from .commands.config import register_config_commands
from .commands.ecosystem import register_ecosystem_commands
from .commands.find_primary import register_find_primary_commands
from .commands.find_secondary import register_find_secondary_commands
from .commands.runtime import register_runtime_commands
from .cli_helpers import (
    _initialize_services,  # noqa: F401
    add_package_helper,  # noqa: F401
    clean_helper,  # noqa: F401
    cypher_helper,  # noqa: F401
    cypher_helper_visual,  # noqa: F401
    delete_helper,  # noqa: F401
    finalize_helper,  # noqa: F401
    index_helper,  # noqa: F401
    index_status_helper,  # noqa: F401
    list_repos_helper,  # noqa: F401
    list_watching_helper,  # noqa: F401
    reindex_helper,  # noqa: F401
    stats_helper,  # noqa: F401
    unwatch_helper,  # noqa: F401
    visualize_helper,  # noqa: F401
    watch_helper,  # noqa: F401
    workspace_index_helper,  # noqa: F401
    workspace_plan_helper,  # noqa: F401
    workspace_status_helper,  # noqa: F401
    workspace_sync_helper,  # noqa: F401
    workspace_watch_helper,  # noqa: F401
)
from .setup_wizard import configure_mcp_client, run_neo4j_setup_wizard  # noqa: F401

console = Console(stderr=True)

app = typer.Typer(
    name="pcg",
    help="PlatformContextGraph: An MCP server for AI-powered code analysis.\n\n[DEPRECATED] 'pcg start' is deprecated. Use 'pcg mcp start' instead.",
    add_completion=True,
)

configure_logging(component="cli", runtime_role="cli")


def _structured_json_logs_enabled() -> bool:
    """Report whether the runtime is in JSON-log mode."""

    configured = os.environ.get("PCG_LOG_FORMAT")
    if configured is None:
        try:
            configured = str(
                config_manager.get_config_value("PCG_LOG_FORMAT") or "json"
            )
        except Exception:
            configured = "json"
    return configured.strip().lower() == "json"


def _console_output_enabled() -> bool:
    """Report whether human-oriented console banners should be emitted."""

    return not _structured_json_logs_enabled()


def _configure_library_loggers() -> None:
    """Configure noisy third-party loggers using the CLI config."""
    try:
        log_level_str = config_manager.get_config_value("LIBRARY_LOG_LEVEL")
        if log_level_str is None:
            log_level_str = "WARNING"
        log_level = getattr(logging, str(log_level_str).upper(), logging.WARNING)
    except (AttributeError, Exception):
        log_level = logging.WARNING

    logging.getLogger("neo4j").setLevel(log_level)
    logging.getLogger("asyncio").setLevel(log_level)
    logging.getLogger("urllib3").setLevel(log_level)


def get_version() -> str:
    """Return the installed package version or a development fallback."""
    try:
        return ensure_v_prefix(pkg_version("platform-context-graph"))
    except PackageNotFoundError:
        return ensure_v_prefix("0.0.0 (dev)")


def _interactive_terminal_attached() -> bool:
    """Report whether the CLI is running with an attached interactive terminal."""

    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


def _enable_local_http_auth_bootstrap_if_interactive() -> None:
    """Allow explicit local CLI startup flows to bootstrap a bearer token once.

    This keeps local `pcg api start` / `pcg serve start` first runs usable without
    weakening non-interactive or Kubernetes startup, which should still fail closed
    unless an explicit token or explicit auto-generation setting is present.
    """

    existing_token = str(os.environ.get("PCG_API_KEY") or "").strip()
    if existing_token:
        return
    if os.environ.get("PCG_AUTO_GENERATE_API_KEY") is not None:
        return
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        return
    if not _interactive_terminal_attached():
        return

    os.environ["PCG_AUTO_GENERATE_API_KEY"] = "true"
    if _console_output_enabled():
        console.print(
            "[yellow]No PCG_API_KEY configured; generating a local bearer token "
            "under PCG_HOME for this interactive startup.[/yellow]"
        )


def start_http_api(
    *, host: str = "127.0.0.1", port: int = 8000, reload: bool = False
) -> None:
    """Start the dedicated HTTP API server.

    Args:
        host: The interface to bind.
        port: The TCP port to bind.
        reload: Whether to enable Uvicorn reload mode.
    """
    from platform_context_graph.api.http_auth import ensure_http_api_key

    import uvicorn

    os.environ.setdefault("PCG_RUNTIME_ROLE", "api")
    _enable_local_http_auth_bootstrap_if_interactive()
    ensure_http_api_key()
    uvicorn.run(
        "platform_context_graph.api.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
        log_config=None,
        access_log=False,
    )


def start_service(
    *, host: str = "0.0.0.0", port: int = 8080, reload: bool = False
) -> None:
    """Start the combined HTTP API and MCP service.

    Args:
        host: The interface to bind.
        port: The TCP port to bind.
        reload: Whether to enable Uvicorn reload mode.
    """
    from platform_context_graph.api.http_auth import ensure_http_api_key

    import uvicorn

    from platform_context_graph.api.app import create_service_app

    os.environ.setdefault("PCG_RUNTIME_ROLE", "api")
    _enable_local_http_auth_bootstrap_if_interactive()
    ensure_http_api_key()
    mcp_server = MCPServer()
    service_app = create_service_app(mcp_server_dependency=lambda: mcp_server)
    uvicorn.run(
        service_app,
        host=host,
        port=port,
        reload=reload,
        log_config=None,
        access_log=False,
    )


def _load_credentials() -> None:
    """Load CLI configuration and credentials into the process environment."""
    from dotenv import dotenv_values

    shell_db_type = os.environ.get("DATABASE_TYPE")
    if shell_db_type and not os.environ.get("PCG_RUNTIME_DB_TYPE"):
        os.environ["PCG_RUNTIME_DB_TYPE"] = shell_db_type

    config_manager.ensure_config_dir()

    config_sources: list[dict[str, str | None]] = []
    config_source_names: list[str] = []

    global_env_path = get_app_env_file()
    if global_env_path.exists():
        try:
            config_sources.append(dotenv_values(str(global_env_path)))
            config_source_names.append(str(global_env_path))
        except Exception as exc:
            if _console_output_enabled():
                console.print(
                    f"[yellow]Warning: Could not load global .env: {exc}[/yellow]"
                )

    try:
        dotenv_path = find_dotenv(usecwd=True, raise_error_if_not_found=False)
        if dotenv_path:
            config_sources.append(dotenv_values(dotenv_path))
            config_source_names.append(str(dotenv_path))
    except Exception as exc:
        if _console_output_enabled():
            console.print(
                f"[yellow]Warning: Could not load .env from current directory: {exc}[/yellow]"
            )

    mcp_file_path = Path.cwd() / "mcp.json"
    if mcp_file_path.exists():
        try:
            with open(mcp_file_path, "r", encoding="utf-8") as handle:
                mcp_config = json.load(handle)
            server_env = (
                mcp_config.get("mcpServers", {})
                .get("PlatformContextGraph", {})
                .get("env", {})
            )
            if server_env:
                config_sources.append(server_env)
                config_source_names.append("mcp.json")
        except Exception as exc:
            if _console_output_enabled():
                console.print(
                    f"[yellow]Warning: Could not load mcp.json: {exc}[/yellow]"
                )

    merged_config: dict[str, str | None] = {}
    for config in config_sources:
        merged_config.update(config)

    for key, value in merged_config.items():
        if value is None:
            continue
        if key in os.environ:
            continue
        os.environ[key] = str(value)

    if config_source_names:
        if _console_output_enabled():
            if len(config_source_names) == 1:
                console.print(
                    f"[dim]Loaded configuration from: {config_source_names[-1]}[/dim]"
                )
            else:
                console.print(
                    "[dim]Loaded configuration from: "
                    f"{', '.join(config_source_names)} (highest priority: {config_source_names[-1]})[/dim]"
                )
    elif _console_output_enabled():
        console.print("[yellow]No configuration file found. Using defaults.[/yellow]")

    runtime_db = os.environ.get("PCG_RUNTIME_DB_TYPE")
    explicit_db = (
        runtime_db
        or os.environ.get("DEFAULT_DATABASE")
        or os.environ.get("DATABASE_TYPE")
    )

    if explicit_db:
        default_db = explicit_db.lower()
    else:
        try:
            from platform_context_graph.core import get_database_manager

            manager = get_database_manager()
            default_db = manager.get_backend_type()
        except Exception:
            from platform_context_graph.core import _is_falkordb_available

            default_db = "falkordb" if _is_falkordb_available() else "kuzudb"

    if default_db == "neo4j":
        has_neo4j_creds = all(
            [
                os.environ.get("NEO4J_URI"),
                os.environ.get("NEO4J_USERNAME"),
                os.environ.get("NEO4J_PASSWORD"),
            ]
        )
        if has_neo4j_creds:
            neo4j_db = os.environ.get("NEO4J_DATABASE")
            if _console_output_enabled():
                if neo4j_db:
                    console.print(
                        f"[cyan]Using database: Neo4j (database: {neo4j_db})[/cyan]"
                    )
                else:
                    console.print("[cyan]Using database: Neo4j[/cyan]")
        elif _console_output_enabled():
            console.print(
                "[yellow]⚠ DEFAULT_DATABASE=neo4j but credentials not found. Falling back to default.[/yellow]"
            )
    elif default_db == "falkordb-remote":
        host = os.environ.get("FALKORDB_HOST")
        if host and _console_output_enabled():
            console.print(f"[cyan]Using database: FalkorDB Remote ({host})[/cyan]")
        elif _console_output_enabled():
            console.print(
                "[yellow]⚠ DATABASE_TYPE=falkordb-remote but FALKORDB_HOST not set.[/yellow]"
            )
    elif default_db == "falkordb":
        if os.environ.get("FALKORDB_HOST"):
            if _console_output_enabled():
                console.print(
                    f"[cyan]Using database: FalkorDB Remote ({os.environ.get('FALKORDB_HOST')})[/cyan]"
                )
        elif _console_output_enabled():
            console.print("[cyan]Using database: FalkorDB[/cyan]")
    elif _console_output_enabled():
        console.print(f"[cyan]Using database: {default_db}[/cyan]")


def _register_command_groups() -> None:
    """Assemble the root Typer app from the extracted command modules."""
    current_module = sys.modules[__name__]
    register_runtime_commands(current_module, app)
    register_config_commands(current_module, app)
    register_bundle_registry_commands(current_module, app)
    register_basic_commands(current_module, app)
    find_app = register_find_primary_commands(current_module, app)
    register_find_secondary_commands(current_module, find_app)
    analyze_app = register_analyze_graph_commands(current_module, app)
    register_analyze_quality_commands(current_module, analyze_app)
    register_ecosystem_commands(current_module, app)


_configure_library_loggers()
_register_command_groups()


if __name__ == "__main__":
    app()
