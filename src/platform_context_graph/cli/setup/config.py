"""Configuration helpers for the Neo4j setup wizard."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


def _api():
    """Return the canonical ``setup_wizard`` module for shared state."""
    from .. import setup_wizard as api

    return api


def _save_neo4j_credentials(creds: dict[str, str]) -> None:
    """Persist Neo4j credentials to the CLI config.

    Args:
        creds: Credential mapping containing Neo4j connection values.
    """
    api = _api()
    from platform_context_graph.cli.config_manager import (
        ensure_config_dir,
        load_config,
        save_config,
    )

    ensure_config_dir()
    config = load_config()
    config["NEO4J_URI"] = creds.get("uri", "")
    config["NEO4J_USERNAME"] = creds.get("username", "neo4j")
    config["NEO4J_PASSWORD"] = creds.get("password", "")
    config["DEFAULT_DATABASE"] = "neo4j"
    save_config(config, preserve_db_credentials=False)

    api.console.print("\n[bold green]✅ Neo4j setup complete![/bold green]")
    api.console.print(
        f"[cyan]📝 Credentials saved to {api.APP_HOME_DISPLAY}/.env[/cyan]"
    )
    api.console.print("[cyan]🔧 Default database set to 'neo4j'[/cyan]")
    api.console.print("\n[dim]You can now use pcg commands with Neo4j:[/dim]")
    api.console.print("[dim]  • pcg index .          - Index your code[/dim]")
    api.console.print("[dim]  • pcg find function    - Search your codebase[/dim]")
    api.console.print("\n[dim]To use pcg as an MCP server in your IDE, run:[/dim]")
    api.console.print("[dim]  pcg mcp setup[/dim]")


def _generate_mcp_json(creds: dict[str, str]) -> None:
    """Generate MCP configuration JSON for Neo4j-backed setups.

    Args:
        creds: Credential mapping containing Neo4j connection values.
    """
    api = _api()
    command, args = api._resolve_cli_command()
    mcp_config = {
        "mcpServers": {
            "PlatformContextGraph": {
                "command": command,
                "args": args,
                "env": {
                    "NEO4J_URI": creds.get("uri", ""),
                    "NEO4J_USERNAME": creds.get("username", "neo4j"),
                    "NEO4J_PASSWORD": creds.get("password", ""),
                },
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

    api.console.print("\n[bold green]Configuration successful![/bold green]")
    api.console.print(
        "Copy the following JSON and add it to your MCP server configuration file:"
    )
    api.console.print(json.dumps(mcp_config, indent=2))

    mcp_file = Path.cwd() / "mcp.json"
    with open(mcp_file, "w", encoding="utf-8") as handle:
        json.dump(mcp_config, handle, indent=2)
    api.console.print(
        f"\n[cyan]For your convenience, the configuration has also been saved to: {mcp_file}[/cyan]"
    )

    api._save_neo4j_credentials(creds)
    api._configure_ide(mcp_config)


def find_jetbrains_mcp_config() -> list[Path] | None:
    """Find the first available JetBrains MCP server config file.

    Returns:
        A single-item list containing the discovered config path, or ``None``
        when no config file could be found.
    """
    bases = [
        Path.home() / ".config" / "JetBrains",
        Path.home() / "Library/Application Support/JetBrains",
        Path.home() / "AppData/Roaming/JetBrains",
    ]
    for base in bases:
        if base.exists():
            for folder in base.iterdir():
                mcp_file = folder / "options" / "mcpServer.xml"
                if mcp_file.exists():
                    return [mcp_file]
    return None


def convert_mcp_json_to_yaml() -> None:
    """Convert the generated ``mcp.json`` file into ``devfile.yaml``."""
    api = _api()
    json_path = Path.cwd() / "mcp.json"
    yaml_path = Path.cwd() / "devfile.yaml"
    if not json_path.exists():
        return

    with open(json_path, "r", encoding="utf-8") as json_file:
        mcp_config = json.load(json_file)
    with open(yaml_path, "w", encoding="utf-8") as yaml_file:
        yaml.dump(mcp_config, yaml_file, default_flow_style=False)
    api.console.print(
        f"[green]Generated devfile.yaml for Amazon Q Developer at {yaml_path}[/green]"
    )
