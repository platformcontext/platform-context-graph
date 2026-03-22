"""Installer helpers for local Neo4j setup."""

from __future__ import annotations

from pathlib import Path


def _api():
    """Return the canonical ``setup_wizard`` module for shared state."""
    from .. import setup_wizard as api

    return api


def setup_docker() -> None:
    """Create Docker assets and start a local Neo4j container."""
    api = _api()
    api.console.print("\n[bold cyan]Setting up Neo4j with Docker...[/bold cyan]")
    api.console.print("Please set a secure password for your Neo4j database:")

    while True:
        passwords = api.prompt(
            [
                {
                    "type": "password",
                    "message": "Enter Neo4j password:",
                    "name": "password",
                },
                {
                    "type": "password",
                    "message": "Confirm password:",
                    "name": "password_confirm",
                },
            ]
        )
        if not passwords:
            return

        password = passwords.get("password", "")
        if password and password == passwords.get("password_confirm"):
            break
        api.console.print(
            "[red]Passwords do not match or are empty. Please try again.[/red]"
        )

    neo4j_dir = Path.cwd() / "neo4j_data"
    for subdir in ["data", "logs", "conf", "plugins"]:
        (neo4j_dir / subdir).mkdir(parents=True, exist_ok=True)

    docker_compose_content = f"""
services:
  neo4j:
    image: neo4j:5.21
    container_name: neo4j-pcg
    restart: unless-stopped
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/{password}
      - NEO4J_ACCEPT_LICENSE_AGREEMENT=yes
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
"""
    compose_file = Path.cwd() / "docker-compose.yml"
    with open(compose_file, "w", encoding="utf-8") as handle:
        handle.write(docker_compose_content)

    api.console.print(
        "[green]✅ docker-compose.yml created with secure password.[/green]"
    )
    api.console.print("\n[cyan]🔍 Validating configuration...[/cyan]")
    is_valid, validation_error = api.DatabaseManager.validate_config(
        api.DEFAULT_NEO4J_URI,
        api.DEFAULT_NEO4J_USERNAME,
        password,
    )
    if not is_valid:
        api.console.print(validation_error)
        api.console.print(
            "\n[red]❌ Configuration validation failed. Please fix the issues and try again.[/red]"
        )
        return

    api.console.print("[green]✅ Configuration format is valid[/green]")
    docker_check = api.run_command(["docker", "--version"], api.console, check=False)
    if not docker_check:
        api.console.print(
            "[red]❌ Docker is not installed or not running. Please install Docker first.[/red]"
        )
        return

    compose_check = api.run_command(
        ["docker", "compose", "version"],
        api.console,
        check=False,
    )
    if not compose_check:
        api.console.print(
            "[red]❌ Docker Compose is not available. Please install Docker Compose.[/red]"
        )
        return

    if not api.prompt(
        [
            {
                "type": "confirm",
                "message": "Ready to launch Neo4j in Docker?",
                "name": "proceed",
                "default": True,
            }
        ]
    ).get("proceed"):
        return

    try:
        api.console.print("[cyan]Pulling Neo4j Docker image...[/cyan]")
        pull_process = api.run_command(
            ["docker", "pull", "neo4j:5.21"],
            api.console,
            check=True,
        )
        if not pull_process:
            api.console.print(
                "[yellow]⚠️ Could not pull image, but continuing anyway...[/yellow]"
            )

        api.console.print("[cyan]Starting Neo4j container...[/cyan]")
        docker_process = api.run_command(
            ["docker", "compose", "up", "-d"],
            api.console,
            check=True,
        )

        if not docker_process:
            return

        api.console.print(
            "[bold green]🚀 Neo4j Docker container started successfully![/bold green]"
        )
        api.console.print(
            "[cyan]Waiting for Neo4j to be ready (this may take 30-60 seconds)...[/cyan]"
        )

        connection_successful = False
        max_attempts = 24
        for attempt in range(max_attempts):
            api.time.sleep(5)
            status_check = api.run_command(
                ["docker", "compose", "ps", "-q", "neo4j"],
                api.console,
                check=False,
            )
            if not status_check or not status_check.stdout.strip():
                api.console.print(
                    "[red]❌ Neo4j container stopped unexpectedly. Check logs with: docker compose logs neo4j[/red]"
                )
                return

            api.console.print(
                f"[yellow]Testing connection... (attempt {attempt + 1}/{max_attempts})[/yellow]"
            )
            is_connected, error_msg = api.DatabaseManager.test_connection(
                api.DEFAULT_NEO4J_URI,
                api.DEFAULT_NEO4J_USERNAME,
                password,
            )
            if is_connected:
                api.console.print(
                    "[bold green]✅ Neo4j is ready and accepting connections![/bold green]"
                )
                connection_successful = True
                break

            if attempt == max_attempts - 1:
                api.console.print(
                    "\n[red]❌ Neo4j did not become ready within 2 minutes.[/red]"
                )
                api.console.print(error_msg)
                api.console.print("\n[cyan]Troubleshooting:[/cyan]")
                api.console.print("  • Check logs: docker compose logs neo4j")
                api.console.print("  • Verify container is running: docker ps")
                api.console.print("  • Try restarting: docker compose restart")
                return

        if not connection_successful:
            return

        creds = {
            "uri": api.DEFAULT_NEO4J_URI,
            "username": api.DEFAULT_NEO4J_USERNAME,
            "password": password,
        }
        api._save_neo4j_credentials(creds)
        api.console.print("\n[bold green]🎉 Setup complete![/bold green]")
        api.console.print("Neo4j is running at:")
        api.console.print("  • Web interface: http://localhost:7474")
        api.console.print("  • Bolt connection: neo4j://localhost:7687")
        api.console.print("\n[cyan]Useful commands:[/cyan]")
        api.console.print("  • Stop: docker compose down")
        api.console.print("  • Restart: docker compose restart")
        api.console.print("  • View logs: docker compose logs neo4j")
    except Exception as exc:
        api.console.print(
            "[bold red]❌ Failed to start Neo4j Docker container:[/bold red] " f"{exc}"
        )
        api.console.print(
            "[cyan]Try checking the logs with: docker compose logs neo4j[/cyan]"
        )


def setup_local_binary() -> None:
    """Automate Neo4j installation on Debian-based Linux systems."""
    api = _api()
    os_name = api.platform.system()
    api.console.print(
        f"Detected Operating System: [bold yellow]{os_name}[/bold yellow]"
    )

    if os_name != "Linux" or not api.os.path.exists("/etc/debian_version"):
        api.console.print(
            "[yellow]Automated installer is designed for Debian-based systems (like Ubuntu).[/yellow]"
        )
        api.console.print(
            "For other systems, please follow the manual installation guide: "
            "[bold blue]https://neo4j.com/docs/operations-manual/current/installation/[/bold blue]"
        )
        return

    api.console.print(
        "[bold]Starting automated Neo4j installation for Ubuntu/Debian.[/bold]"
    )
    api.console.print(
        "[yellow]This will run several commands with 'sudo'. You will be prompted for your password.[/yellow]"
    )
    if not api.prompt(
        [
            {
                "type": "confirm",
                "message": "Do you want to proceed?",
                "name": "proceed",
                "default": True,
            }
        ]
    ).get("proceed"):
        return

    install_commands = [
        ("Creating keyring directory", ["sudo", "mkdir", "-p", "/etc/apt/keyrings"]),
        (
            "Adding Neo4j GPG key",
            "wget -qO- https://debian.neo4j.com/neotechnology.gpg.key | "
            "sudo gpg --dearmor --yes -o /etc/apt/keyrings/neotechnology.gpg",
            True,
        ),
        (
            "Adding Neo4j repository",
            "echo 'deb [signed-by=/etc/apt/keyrings/neotechnology.gpg] "
            "https://debian.neo4j.com stable 5' | sudo tee "
            "/etc/apt/sources.list.d/neo4j.list > /dev/null",
            True,
        ),
        ("Updating apt sources", ["sudo", "apt-get", "-qq", "update"]),
        (
            "Installing latest Neo4j and Cypher Shell",
            ["sudo", "apt-get", "install", "-qq", "-y", "neo4j", "cypher-shell"],
        ),
    ]

    for desc, cmd, use_shell in [
        (command[0], command[1], command[2] if len(command) > 2 else False)
        for command in install_commands
    ]:
        api.console.print(f"\n[bold]Step: {desc}...[/bold]")
        if not api.run_command(cmd, api.console, shell=use_shell):
            api.console.print(
                f"[bold red]Failed on step: {desc}. Aborting installation.[/bold red]"
            )
            return

    api.console.print("\n[bold green]Neo4j installed successfully![/bold green]")
    api.console.print("\n[bold]Please set the initial password for the 'neo4j' user.")

    new_password = ""
    while True:
        passwords = api.prompt(
            [
                {
                    "type": "password",
                    "message": "Enter a new password for Neo4j:",
                    "name": "password",
                },
                {
                    "type": "password",
                    "message": "Confirm the new password:",
                    "name": "password_confirm",
                },
            ]
        )
        if not passwords:
            return
        new_password = passwords.get("password")
        if new_password and new_password == passwords.get("password_confirm"):
            break
        api.console.print(
            "[red]Passwords do not match or are empty. Please try again.[/red]"
        )

    api.console.print("\n[bold]Stopping Neo4j to set the password...")
    if not api.run_command(["sudo", "systemctl", "stop", "neo4j"], api.console):
        api.console.print(
            "[bold red]Could not stop Neo4j service. Aborting.[/bold red]"
        )
        return

    api.console.print("\n[bold]Setting initial password using neo4j-admin...")
    pw_command = [
        "sudo",
        "-u",
        "neo4j",
        "neo4j-admin",
        "dbms",
        "set-initial-password",
        new_password,
    ]
    if not api.run_command(pw_command, api.console, check=True):
        api.console.print(
            "[bold red]Failed to set the initial password. Please check the logs.[/bold red]"
        )
        api.run_command(["sudo", "systemctl", "start", "neo4j"], api.console)
        return

    api.console.print("\n[bold]Starting Neo4j service...")
    if not api.run_command(["sudo", "systemctl", "start", "neo4j"], api.console):
        api.console.print(
            "[bold red]Failed to start Neo4j service after setting password.[/bold red]"
        )
        return

    api.console.print("\n[bold]Enabling Neo4j service to start on boot...")
    if not api.run_command(["sudo", "systemctl", "enable", "neo4j"], api.console):
        api.console.print(
            "[bold yellow]Could not enable Neo4j service. You may need to start it manually after reboot.[/bold yellow]"
        )

    api.console.print("[bold green]Password set and service started.[/bold green]")
    api.console.print(
        "\n[yellow]Waiting 10 seconds for the database to become available..."
    )
    api.time.sleep(10)

    creds = {
        "uri": "neo4j://localhost:7687",
        "username": "neo4j",
        "password": new_password,
    }
    api._save_neo4j_credentials(creds)
    api.console.print(
        "\n[bold green]All done! Your local Neo4j instance is ready to use.[/bold green]"
    )
