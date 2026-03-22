"""Runtime entrypoints for the Neo4j setup wizard."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _api():
    """Return the canonical ``setup_wizard`` module for shared state."""
    from .. import setup_wizard as api

    return api


def get_project_root() -> Path:
    """Return the current working directory for CLI setup operations.

    Returns:
        The directory where the user invoked ``pcg``.
    """
    return Path.cwd()


def run_command(
    command,
    console,
    shell: bool = False,
    check: bool = True,
    input_text: str | None = None,
):
    """Run a subprocess command and capture its output.

    Args:
        command: Command list or shell string to execute.
        console: Rich console used for user-facing output.
        shell: Whether to run the command through the shell.
        check: Whether non-zero exits should raise ``CalledProcessError``.
        input_text: Optional stdin passed to the subprocess.

    Returns:
        The completed process on success, otherwise ``None``.
    """
    cmd_str = command if isinstance(command, str) else " ".join(command)
    console.print(f"[cyan]$ {cmd_str}[/cyan]")
    try:
        return subprocess.run(
            command,
            shell=shell,
            check=check,
            capture_output=True,
            text=True,
            timeout=300,
            input=input_text,
        )
    except subprocess.CalledProcessError as exc:
        console.print(f"[bold red]Error executing command:[/bold red] {cmd_str}")
        if exc.stdout:
            console.print(f"[red]STDOUT: {exc.stdout}[/red]")
        if exc.stderr:
            console.print(f"[red]STDERR: {exc.stderr}[/red]")
        return None
    except subprocess.TimeoutExpired:
        console.print(f"[bold red]Command timed out:[/bold red] {cmd_str}")
        return None


def run_neo4j_setup_wizard() -> None:
    """Guide the user through choosing a Neo4j setup path."""
    api = _api()
    api.console.print("[bold cyan]Welcome to the Neo4j Setup Wizard![/bold cyan]")
    result = api.prompt(
        [
            {
                "type": "list",
                "message": "Where do you want to setup your Neo4j database?",
                "choices": [
                    "Local (Recommended: I'll help you run it on this machine)",
                    "Hosted (Connect to a remote database like AuraDB)",
                    "I already have an existing neo4j instance running.",
                ],
                "name": "db_location",
            }
        ]
    )
    db_location = result.get("db_location")

    if db_location and "Hosted" in db_location:
        api.setup_hosted_db()
    elif db_location and "Local" in db_location:
        api.setup_local_db()
    elif db_location:
        api.setup_existing_db()


def configure_mcp_client() -> None:
    """Generate MCP client configuration from the active CLI settings."""
    api = _api()
    api.console.print("[bold cyan]MCP Client Configuration[/bold cyan]\n")
    api.console.print(
        "This will configure PlatformContextGraph integration with your IDE or CLI tool."
    )
    api.console.print(
        "PlatformContextGraph works with FalkorDB by default (no database setup needed).\n"
    )

    try:
        from platform_context_graph.cli.config_manager import load_config

        config = load_config()
    except Exception as exc:
        api.console.print(
            f"[yellow]Warning: Could not load configuration: {exc}[/yellow]"
        )
        config = {}

    env_vars: dict[str, str] = {}
    env_file = api.get_app_env_file()
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        if key in {
                            "NEO4J_URI",
                            "NEO4J_USERNAME",
                            "NEO4J_PASSWORD",
                            "NEO4J_DATABASE",
                        }:
                            env_vars[key] = value.strip()
        except Exception:
            pass

    for key, value in config.items():
        if key in {"NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"}:
            continue
        if "PATH" in key and value:
            path_obj = Path(value)
            if not path_obj.is_absolute():
                value = str(path_obj.resolve())
        env_vars[key] = value

    command, args = api._resolve_cli_command()
    mcp_config = {
        "mcpServers": {
            "PlatformContextGraph": {
                "command": command,
                "args": args,
                "env": env_vars,
                "tools": {
                    "alwaysAllow": [
                        "add_code_to_graph",
                        "add_package_to_graph",
                        "check_job_status",
                        "list_jobs",
                        "find_code",
                        "analyze_code_relationships",
                        "watch_directory",
                        "find_dead_code",
                        "execute_cypher_query",
                        "calculate_cyclomatic_complexity",
                        "find_most_complex_functions",
                        "list_indexed_repositories",
                        "delete_repository",
                        "list_watched_paths",
                        "unwatch_directory",
                        "visualize_graph_query",
                    ],
                    "disabled": False,
                },
                "disabled": False,
                "alwaysAllow": [],
            }
        }
    }

    api.console.print("\n[bold green]Configuration generated![/bold green]")
    api.console.print(
        "Copy the following JSON and add it to your MCP server configuration file:"
    )
    api.console.print(json.dumps(mcp_config, indent=2))

    mcp_file = Path.cwd() / "mcp.json"
    with open(mcp_file, "w", encoding="utf-8") as handle:
        json.dump(mcp_config, handle, indent=2)
    api.console.print(f"\n[cyan]Configuration saved to: {mcp_file}[/cyan]")

    api._configure_ide(mcp_config)
    api.console.print(
        "\n[bold green]✅ MCP Client configuration complete![/bold green]"
    )
    api.console.print(
        "[cyan]You can now run 'pcg mcp start' to launch the server.[/cyan]"
    )
    api.console.print(
        "[yellow]💡 Tip: To update MCP config after changing settings, re-run 'pcg mcp setup'[/yellow]\n"
    )


def find_latest_neo4j_creds_file():
    """Find the newest downloaded Neo4j credentials export.

    Returns:
        The most recent ``Neo4j*.txt`` file from the user's Downloads directory,
        or ``None`` when no matching file exists.
    """
    downloads_path = Path.home() / "Downloads"
    if not downloads_path.exists():
        return None

    cred_files = list(downloads_path.glob("Neo4j*.txt"))
    if not cred_files:
        return None

    return max(cred_files, key=lambda file_path: file_path.stat().st_mtime)
