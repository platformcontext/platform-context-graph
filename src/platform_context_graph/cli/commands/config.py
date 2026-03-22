"""Configuration command registration for the CLI entrypoint."""

from __future__ import annotations

from typing import Any

import typer


def register_config_commands(main_module: Any, app: typer.Typer) -> None:
    """Register configuration commands on the root CLI app.

    Args:
        main_module: The imported ``platform_context_graph.cli.main`` module.
        app: The root Typer application.
    """
    config_app = typer.Typer(help="Manage configuration settings")
    app.add_typer(config_app, name="config")

    @config_app.command("show")
    def config_show() -> None:
        """Display the current configuration settings."""
        main_module.config_manager.show_config()

    @config_app.command("set")
    def config_set(
        key: str = typer.Argument(..., help="Configuration key to set"),
        value: str = typer.Argument(..., help="Value to set"),
    ) -> None:
        """Set one configuration value."""
        main_module.config_manager.set_config_value(key, value)

    @config_app.command("reset")
    def config_reset() -> None:
        """Reset all configuration to default values."""
        if typer.confirm(
            "Are you sure you want to reset all configuration to defaults?",
            default=False,
        ):
            main_module.config_manager.reset_config()
        else:
            main_module.console.print("[yellow]Reset cancelled[/yellow]")

    @config_app.command("db")
    def config_db(
        backend: str = typer.Argument(
            ..., help="Database backend: 'neo4j' or 'falkordb'"
        )
    ) -> None:
        """Quickly switch the default database backend."""
        normalized_backend = backend.lower()
        if normalized_backend not in ["falkordb", "falkordb-remote", "neo4j"]:
            main_module.console.print(
                f"[bold red]Invalid backend: {normalized_backend}[/bold red]"
            )
            main_module.console.print(
                "Must be 'falkordb', 'falkordb-remote', or 'neo4j'"
            )
            raise typer.Exit(code=1)

        main_module.config_manager.set_config_value(
            "DEFAULT_DATABASE", normalized_backend
        )
        main_module.console.print(
            f"[green]✔ Default database switched to {normalized_backend}[/green]"
        )
