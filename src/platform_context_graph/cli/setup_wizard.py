"""Public Neo4j setup wizard entrypoints for the CLI."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml
from InquirerPy.resolver import prompt
from rich.console import Console

from platform_context_graph.core.database import DatabaseManager
from platform_context_graph.paths import APP_HOME_DISPLAY, get_app_env_file
from .setup.config import (
    _generate_mcp_json,
    _save_neo4j_credentials,
    convert_mcp_json_to_yaml,
    find_jetbrains_mcp_config,
)
from .setup.database import (
    setup_existing_db,
    setup_hosted_db,
    setup_local_db,
)
from .setup.ide import _configure_ide
from .setup.installers import setup_docker, setup_local_binary
from .setup.runtime import (
    configure_mcp_client,
    find_latest_neo4j_creds_file,
    get_project_root,
    run_command,
    run_neo4j_setup_wizard,
)

console = Console()

DEFAULT_NEO4J_URI = "neo4j://localhost:7687"
DEFAULT_NEO4J_USERNAME = "neo4j"
DEFAULT_NEO4J_BOLT_PORT = 7687
DEFAULT_NEO4J_HTTP_PORT = 7474


def _resolve_cli_command() -> tuple[str, list[str]]:
    """Resolve the preferred CLI command for generated MCP configs.

    Returns:
        The executable path and CLI arguments used to start the MCP server.
    """
    cli_path = shutil.which("pcg") or sys.executable
    if "python" in Path(cli_path).name:
        return cli_path, ["-m", "platform_context_graph", "mcp", "start"]
    return cli_path, ["mcp", "start"]


__all__ = [
    "APP_HOME_DISPLAY",
    "DEFAULT_NEO4J_BOLT_PORT",
    "DEFAULT_NEO4J_HTTP_PORT",
    "DEFAULT_NEO4J_URI",
    "DEFAULT_NEO4J_USERNAME",
    "DatabaseManager",
    "_configure_ide",
    "_generate_mcp_json",
    "_resolve_cli_command",
    "_save_neo4j_credentials",
    "configure_mcp_client",
    "console",
    "convert_mcp_json_to_yaml",
    "find_jetbrains_mcp_config",
    "find_latest_neo4j_creds_file",
    "get_app_env_file",
    "get_project_root",
    "prompt",
    "run_command",
    "run_neo4j_setup_wizard",
    "setup_docker",
    "setup_existing_db",
    "setup_hosted_db",
    "setup_local_binary",
    "setup_local_db",
]
