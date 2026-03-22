"""IDE configuration helpers for the Neo4j setup wizard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _api():
    """Return the canonical ``setup_wizard`` module for shared state."""
    from .. import setup_wizard as api

    return api


def _build_config_paths() -> dict[str, list[Path] | None]:
    """Build the supported IDE configuration file candidates.

    Returns:
        A mapping from IDE display name to candidate configuration paths.
    """
    api = _api()
    return {
        "VS Code": [
            api.Path.home() / ".config" / "Code" / "User" / "settings.json",
            api.Path.home()
            / "Library"
            / "Application Support"
            / "Code"
            / "User"
            / "settings.json",
            api.Path.home() / "AppData" / "Roaming" / "Code" / "User" / "settings.json",
        ],
        "Cursor/CLI": [
            api.Path.home() / ".cursor" / "settings.json",
            api.Path.home() / ".config" / "cursor" / "settings.json",
            api.Path.home()
            / "Library"
            / "Application Support"
            / "cursor"
            / "settings.json",
            api.Path.home() / "AppData" / "Roaming" / "cursor" / "settings.json",
            api.Path.home() / ".config" / "Cursor" / "User" / "settings.json",
        ],
        "Windsurf": [
            api.Path.home() / ".windsurf" / "settings.json",
            api.Path.home() / ".config" / "windsurf" / "settings.json",
            api.Path.home()
            / "Library"
            / "Application Support"
            / "windsurf"
            / "settings.json",
            api.Path.home() / "AppData" / "Roaming" / "windsurf" / "settings.json",
            api.Path.home() / ".config" / "Windsurf" / "User" / "settings.json",
        ],
        "Claude code": [api.Path.home() / ".claude.json"],
        "Gemini CLI": [api.Path.home() / ".gemini" / "settings.json"],
        "ChatGPT Codex": [
            api.Path.home() / ".openai" / "mcp_settings.json",
            api.Path.home() / ".config" / "openai" / "settings.json",
            api.Path.home() / "AppData" / "Roaming" / "OpenAI" / "settings.json",
        ],
        "Cline": [
            api.Path.home()
            / ".config"
            / "Code"
            / "User"
            / "globalStorage"
            / "saoudrizwan.claude-dev"
            / "settings"
            / "cline_mcp_settings.json",
            api.Path.home()
            / ".config"
            / "Code - OSS"
            / "User"
            / "globalStorage"
            / "saoudrizwan.claude-dev"
            / "settings"
            / "cline_mcp_settings.json",
            api.Path.home()
            / "Library"
            / "Application Support"
            / "Code"
            / "User"
            / "globalStorage"
            / "saoudrizwan.claude-dev"
            / "settings"
            / "cline_mcp_settings.json",
            api.Path.home()
            / "AppData"
            / "Roaming"
            / "Code"
            / "User"
            / "globalStorage"
            / "saoudrizwan.claude-dev"
            / "settings"
            / "cline_mcp_settings.json",
        ],
        "JetBrainsAI": api.find_jetbrains_mcp_config(),
        "RooCode": [
            api.Path.home() / ".config" / "Code" / "User" / "settings.json",
            api.Path.home() / "AppData" / "Roaming" / "Code" / "User" / "settings.json",
            api.Path.home()
            / "Library"
            / "Application Support"
            / "Code"
            / "User"
            / "settings.json",
        ],
        "Aider": [
            api.Path.home() / ".aider" / "settings.json",
            api.Path.home() / ".config" / "aider" / "settings.json",
            api.Path.home()
            / "Library"
            / "Application Support"
            / "aider"
            / "settings.json",
            api.Path.home() / "AppData" / "Roaming" / "aider" / "settings.json",
            api.Path.home() / ".config" / "Aider" / "User" / "settings.json",
        ],
        "Kiro": [
            api.Path.home() / ".kiro" / "settings" / "mcp.json",
            api.Path.home() / ".config" / "kiro" / "settings" / "mcp.json",
            api.Path.home() / "AppData" / "Roaming" / "Kiro" / "settings" / "mcp.json",
        ],
        "Antigravity": [
            api.Path.home() / ".antigravity" / "mcp_settings.json",
            api.Path.home() / ".config" / "antigravity" / "mcp_settings.json",
            api.Path.home()
            / "AppData"
            / "Roaming"
            / "Antigravity"
            / "mcp_settings.json",
        ],
    }


def _choose_target_path(paths_to_check: list[Path]) -> Path | None:
    """Pick an existing config path or a creatable parent directory.

    Args:
        paths_to_check: Candidate configuration file paths.

    Returns:
        The selected target path, or ``None`` when no valid location exists.
    """
    for path in paths_to_check:
        if path.exists():
            return path

    for path in paths_to_check:
        if path.parent.exists():
            return path

    return None


def _load_settings(target_path: Path) -> dict[str, Any] | None:
    """Load a JSON settings file from disk.

    Args:
        target_path: Settings file location.

    Returns:
        The decoded settings object, or ``None`` when the file does not contain
        a JSON object.
    """
    api = _api()
    try:
        with open(target_path, "r", encoding="utf-8") as handle:
            try:
                settings = json.load(handle)
            except json.JSONDecodeError:
                settings = {}
    except FileNotFoundError:
        settings = {}

    if not isinstance(settings, dict):
        api.console.print(
            f"[red]Error: Configuration file at {target_path} is not a valid JSON object.[/red]"
        )
        return None
    return settings


def _configure_ide(mcp_config: dict[str, Any]) -> None:
    """Prompt for an IDE and merge the MCP config into its settings.

    Args:
        mcp_config: Generated MCP configuration payload.
    """
    api = _api()
    result = api.prompt(
        [
            {
                "type": "confirm",
                "message": (
                    "Automatically configure your IDE/CLI (VS Code, Cursor, Windsurf, "
                    "Claude, Gemini, Cline, RooCode, ChatGPT Codex, Amazon Q Developer, "
                    "Aider, Kiro, Antigravity)?"
                ),
                "name": "configure_ide",
                "default": True,
            }
        ]
    )
    if not result or not result.get("configure_ide"):
        api.console.print(
            "\n[cyan]Skipping automatic IDE configuration. You can add the MCP server manually.[/cyan]"
        )
        return

    ide_result = api.prompt(
        [
            {
                "type": "list",
                "message": "Choose your IDE/CLI to configure:",
                "choices": [
                    "VS Code",
                    "Cursor",
                    "Windsurf",
                    "Claude code",
                    "Gemini CLI",
                    "ChatGPT Codex",
                    "Cline",
                    "RooCode",
                    "Amazon Q Developer",
                    "JetBrainsAI",
                    "Aider",
                    "Kiro",
                    "Antigravity",
                    "None of the above",
                ],
                "name": "ide_choice",
            }
        ]
    )
    ide_choice = ide_result.get("ide_choice")

    if not ide_choice or ide_choice == "None of the above":
        api.console.print(
            "\n[cyan]You can add the MCP server manually to your IDE/CLI.[/cyan]"
        )
        return

    if ide_choice not in [
        "VS Code",
        "Cursor",
        "Claude code",
        "Gemini CLI",
        "ChatGPT Codex",
        "Cline",
        "Windsurf",
        "RooCode",
        "Amazon Q Developer",
        "JetBrainsAI",
        "Aider",
        "Kiro",
        "Antigravity",
    ]:
        return

    api.console.print(f"\n[bold cyan]Configuring for {ide_choice}...[/bold cyan]")
    if ide_choice == "Amazon Q Developer":
        api.convert_mcp_json_to_yaml()
        return

    config_paths = _build_config_paths()
    paths_to_check = config_paths.get(ide_choice, []) or []
    target_path = _choose_target_path(paths_to_check)
    if not target_path:
        api.console.print(
            f"[yellow]Could not automatically find or create the configuration directory for {ide_choice}.[/yellow]"
        )
        api.console.print(
            "Please add the MCP configuration manually from the `mcp.json` file generated above."
        )
        return

    api.console.print(f"Using configuration file at: {target_path}")
    settings = _load_settings(target_path)
    if settings is None:
        return

    settings.setdefault("mcpServers", {})
    settings["mcpServers"].update(mcp_config["mcpServers"])

    try:
        with open(target_path, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
        api.console.print(
            f"[green]Successfully updated {ide_choice} configuration.[/green]"
        )
    except Exception as exc:
        api.console.print(f"[red]Failed to write to configuration file: {exc}[/red]")
