"""Database-selection flows for the Neo4j setup wizard."""

from __future__ import annotations

from pathlib import Path


def _api():
    """Return the canonical ``setup_wizard`` module for shared state."""
    from .. import setup_wizard as api

    return api


def _parse_credentials_file(file_to_parse: Path) -> dict[str, str]:
    """Parse Neo4j credentials from a file.

    Args:
        file_to_parse: Credentials file selected by the user.

    Returns:
        Parsed credential mapping.
    """
    creds: dict[str, str] = {}
    with open(file_to_parse, "r", encoding="utf-8") as handle:
        for line in handle:
            if "=" not in line:
                continue
            key, value = line.strip().split("=", 1)
            if key == "NEO4J_URI":
                creds["uri"] = value
            elif key == "NEO4J_USERNAME":
                creds["username"] = value
            elif key == "NEO4J_PASSWORD":
                creds["password"] = value
    return creds


def setup_existing_db() -> None:
    """Guide the user through connecting to an existing Neo4j instance."""
    api = _api()
    api.console.print(
        "\nTo connect to an existing Neo4j database, you'll need your connection credentials."
    )
    api.console.print(
        "If you don't have credentials for the database, you can create a new one using 'Local' installation in the previous menu."
    )

    result = api.prompt(
        [
            {
                "type": "list",
                "message": "How would you like to add your Neo4j credentials?",
                "choices": ["Add credentials from file", "Add credentials manually"],
                "name": "cred_method",
            }
        ]
    )
    cred_method = result.get("cred_method")

    creds: dict[str, str] = {}
    if cred_method and "file" in cred_method:
        latest_file = api.find_latest_neo4j_creds_file()
        file_to_parse = None
        if latest_file:
            if api.prompt(
                [
                    {
                        "type": "confirm",
                        "message": f"Found a credentials file: {latest_file}. Use this file?",
                        "name": "use_latest",
                        "default": True,
                    }
                ]
            ).get("use_latest"):
                file_to_parse = latest_file

        if not file_to_parse:
            file_path_str = api.prompt(
                [
                    {
                        "type": "input",
                        "message": "Please enter the path to your credentials file:",
                        "name": "cred_file_path",
                    }
                ]
            ).get("cred_file_path", "")
            path = Path(file_path_str.strip())
            if path.exists() and path.is_file():
                file_to_parse = path
            else:
                api.console.print(
                    "[red]❌ The specified file path does not exist or is not a file.[/red]"
                )
                return

        if file_to_parse:
            try:
                creds = _parse_credentials_file(file_to_parse)
            except Exception as exc:
                api.console.print(
                    f"[red]❌ Failed to parse credentials file: {exc}[/red]"
                )
                return
    elif cred_method:
        api.console.print("Please enter your Neo4j connection details.")
        while True:
            manual_creds = api.prompt(
                [
                    {
                        "type": "input",
                        "message": "URI (e.g., 'neo4j://localhost:7687'):",
                        "name": "uri",
                        "default": "neo4j://localhost:7687",
                    },
                    {
                        "type": "input",
                        "message": "Username:",
                        "name": "username",
                        "default": "neo4j",
                    },
                    {"type": "password", "message": "Password:", "name": "password"},
                ]
            )
            if not manual_creds:
                return

            api.console.print("\n[cyan]🔍 Validating configuration...[/cyan]")
            is_valid, validation_error = api.DatabaseManager.validate_config(
                manual_creds.get("uri", ""),
                manual_creds.get("username", ""),
                manual_creds.get("password", ""),
            )
            if not is_valid:
                api.console.print(validation_error)
                api.console.print(
                    "\n[red]❌ Invalid configuration. Please try again.[/red]\n"
                )
                continue

            api.console.print("[green]✅ Configuration format is valid[/green]")
            api.console.print("\n[cyan]🔗 Testing connection...[/cyan]")
            is_connected, error_msg = api.DatabaseManager.test_connection(
                manual_creds.get("uri", ""),
                manual_creds.get("username", ""),
                manual_creds.get("password", ""),
            )
            if not is_connected:
                api.console.print(error_msg)
                retry = api.prompt(
                    [
                        {
                            "type": "confirm",
                            "message": "Connection failed. Try again with different credentials?",
                            "name": "retry",
                            "default": True,
                        }
                    ]
                )
                if not retry.get("retry"):
                    return
                continue

            api.console.print("[green]✅ Connection successful![/green]")
            creds = manual_creds
            break

    if creds.get("uri") and creds.get("password"):
        api._save_neo4j_credentials(creds)
    else:
        api.console.print("[red]❌ Incomplete credentials. Please try again.[/red]")


def setup_hosted_db() -> None:
    """Guide the user through connecting to a hosted Neo4j instance."""
    api = _api()
    api.console.print(
        "\nTo connect to a hosted Neo4j database, you'll need your connection credentials."
    )
    api.console.print(
        "[yellow]Warning: You are configuring to connect to a remote/hosted Neo4j database. Ensure your credentials are secure.[/yellow]"
    )
    api.console.print(
        "If you don't have a hosted database, you can create a free one at [bold blue]https://neo4j.com/product/auradb/[/bold blue] (click 'Start free')."
    )

    result = api.prompt(
        [
            {
                "type": "list",
                "message": "How would you like to add your Neo4j credentials?",
                "choices": ["Add credentials from file", "Add credentials manually"],
                "name": "cred_method",
            }
        ]
    )
    cred_method = result.get("cred_method")

    creds: dict[str, str] = {}
    if cred_method and "file" in cred_method:
        latest_file = api.find_latest_neo4j_creds_file()
        file_to_parse = None
        if latest_file:
            if api.prompt(
                [
                    {
                        "type": "confirm",
                        "message": f"Found a credentials file: {latest_file}. Use this file?",
                        "name": "use_latest",
                        "default": True,
                    }
                ]
            ).get("use_latest"):
                file_to_parse = latest_file

        if not file_to_parse:
            file_path_str = api.prompt(
                [
                    {
                        "type": "input",
                        "message": "Please enter the path to your credentials file:",
                        "name": "cred_file_path",
                    }
                ]
            ).get("cred_file_path", "")
            path = Path(file_path_str.strip())
            if path.exists() and path.is_file():
                file_to_parse = path
            else:
                api.console.print(
                    "[red]❌ The specified file path does not exist or is not a file.[/red]"
                )
                return

        if file_to_parse:
            try:
                creds = _parse_credentials_file(file_to_parse)
            except Exception as exc:
                api.console.print(
                    f"[red]❌ Failed to parse credentials file: {exc}[/red]"
                )
                return
    elif cred_method:
        api.console.print("Please enter your remote Neo4j connection details.")
        while True:
            manual_creds = api.prompt(
                [
                    {
                        "type": "input",
                        "message": "URI (e.g., neo4j+s://xxxx.databases.neo4j.io):",
                        "name": "uri",
                    },
                    {
                        "type": "input",
                        "message": "Username:",
                        "name": "username",
                        "default": "neo4j",
                    },
                    {"type": "password", "message": "Password:", "name": "password"},
                ]
            )
            if not manual_creds:
                return

            api.console.print("\n[cyan]🔍 Validating configuration...[/cyan]")
            is_valid, validation_error = api.DatabaseManager.validate_config(
                manual_creds.get("uri", ""),
                manual_creds.get("username", ""),
                manual_creds.get("password", ""),
            )
            if not is_valid:
                api.console.print(validation_error)
                api.console.print(
                    "\n[red]❌ Invalid configuration. Please try again.[/red]\n"
                )
                continue

            api.console.print("[green]✅ Configuration format is valid[/green]")
            api.console.print("\n[cyan]🔗 Testing connection...[/cyan]")
            is_connected, error_msg = api.DatabaseManager.test_connection(
                manual_creds.get("uri", ""),
                manual_creds.get("username", ""),
                manual_creds.get("password", ""),
            )
            if not is_connected:
                api.console.print(error_msg)
                retry = api.prompt(
                    [
                        {
                            "type": "confirm",
                            "message": "Connection failed. Try again with different credentials?",
                            "name": "retry",
                            "default": True,
                        }
                    ]
                )
                if not retry.get("retry"):
                    return
                continue

            api.console.print("[green]✅ Connection successful![/green]")
            creds = manual_creds
            break

    if creds.get("uri") and creds.get("password"):
        api._save_neo4j_credentials(creds)
    else:
        api.console.print("[red]❌ Incomplete credentials. Please try again.[/red]")


def setup_local_db() -> None:
    """Guide the user through setting up a local Neo4j instance."""
    api = _api()
    result = api.prompt(
        [
            {
                "type": "list",
                "message": "How would you like to run Neo4j locally?",
                "choices": ["Docker (Easiest)", "Local Binary (Advanced)"],
                "name": "local_method",
            }
        ]
    )
    local_method = result.get("local_method")

    if local_method and "Docker" in local_method:
        api.setup_docker()
    elif local_method:
        if api.platform.system() == "Darwin":
            from .macos import setup_macos_binary

            setup_macos_binary(
                api.console,
                api.prompt,
                api.run_command,
                api._save_neo4j_credentials,
            )
        else:
            api.setup_local_binary()
