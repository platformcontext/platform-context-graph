"""Secondary find command registration for the CLI entrypoint."""

from __future__ import annotations

from typing import Any

import typer
from rich import box
from rich.table import Table


def register_find_secondary_commands(main_module: Any, find_app: typer.Typer) -> None:
    """Register the extended ``pcg find`` commands.

    Args:
        main_module: The imported ``platform_context_graph.cli.main`` module.
        find_app: The shared ``find`` Typer sub-application.
    """

    @find_app.command("variable")
    def find_by_variable(
        name: str = typer.Argument(..., help="Variable name to search for")
    ) -> None:
        """Find variables by name."""
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services

        try:
            results = code_finder.find_by_variable_name(name)
            if not results:
                main_module.console.print(
                    f"[yellow]No variables found with name '{name}'[/yellow]"
                )
                return

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Name", style="cyan")
            table.add_column("Location", style="dim", overflow="fold")
            table.add_column("Context", style="yellow")

            for item in results:
                path = item.get("path", "") or ""
                line_str = str(item.get("line_number", ""))
                location_str = f"{path}:{line_str}" if line_str else path
                table.add_row(
                    item.get("name", ""),
                    location_str,
                    item.get("context", "") or "module",
                )

            main_module.console.print(
                f"[cyan]Found {len(results)} variable(s) named '{name}':[/cyan]"
            )
            main_module.console.print(table)
        finally:
            db_manager.close_driver()

    @find_app.command("content")
    def find_by_content_search(
        query: str = typer.Argument(
            ..., help="Text to search for in source code and docstrings"
        )
    ) -> None:
        """Search code content using the full-text index."""
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services

        try:
            try:
                results = code_finder.find_by_content(query)
            except Exception as exc:
                error_msg = str(exc).lower()
                is_falkor_fulltext_issue = (
                    "fulltext" in error_msg or "db.index.fulltext" in error_msg
                ) and "Falkor" in db_manager.__class__.__name__
                if not is_falkor_fulltext_issue:
                    raise

                main_module.console.print(
                    "\n[bold red]❌ Full-text search is not supported on FalkorDB[/bold red]\n"
                )
                main_module.console.print("[yellow]💡 You have two options:[/yellow]\n")
                main_module.console.print("  1. [cyan]Switch to Neo4j:[/cyan]")
                main_module.console.print(
                    f'     [dim]pcg --database neo4j find content "{query}"[/dim]\n'
                )
                main_module.console.print(
                    "  2. [cyan]Use pattern search instead:[/cyan]"
                )
                main_module.console.print(f'     [dim]pcg find pattern "{query}"[/dim]')
                main_module.console.print(
                    "     [dim](searches in names only, not source code)[/dim]\n"
                )
                return

            if not results:
                main_module.console.print(
                    f"[yellow]No content matches found for '{query}'[/yellow]"
                )
                return

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="blue")
            table.add_column("Location", style="dim", overflow="fold")

            for item in results:
                path = item.get("path", "") or ""
                line_str = str(item.get("line_number", ""))
                location_str = f"{path}:{line_str}" if line_str else path
                table.add_row(
                    item.get("name", ""), item.get("type", "Unknown"), location_str
                )

            main_module.console.print(
                f"[cyan]Found {len(results)} content match(es) for '{query}':[/cyan]"
            )
            main_module.console.print(table)
        finally:
            db_manager.close_driver()

    @find_app.command("decorator")
    def find_by_decorator_search(
        decorator: str = typer.Argument(..., help="Decorator name to search for"),
        file: str | None = typer.Option(
            None, "--file", "-f", help="Specific file path"
        ),
    ) -> None:
        """Find functions with a specific decorator."""
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services

        try:
            results = code_finder.find_functions_by_decorator(decorator, file)
            if not results:
                main_module.console.print(
                    f"[yellow]No functions found with decorator '@{decorator}'[/yellow]"
                )
                return

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Function", style="cyan")
            table.add_column("Location", style="dim", overflow="fold")
            table.add_column("Decorators", style="yellow")

            for item in results:
                decorators_str = ", ".join(item.get("decorators", []))
                path = item.get("path", "") or ""
                line_str = str(item.get("line_number", ""))
                location_str = f"{path}:{line_str}" if line_str else path
                table.add_row(
                    item.get("function_name", ""), location_str, decorators_str
                )

            main_module.console.print(
                f"[cyan]Found {len(results)} function(s) with decorator '@{decorator}':[/cyan]"
            )
            main_module.console.print(table)
        finally:
            db_manager.close_driver()

    @find_app.command("argument")
    def find_by_argument_search(
        argument: str = typer.Argument(
            ..., help="Argument/parameter name to search for"
        ),
        file: str | None = typer.Option(
            None, "--file", "-f", help="Specific file path"
        ),
    ) -> None:
        """Find functions that take a specific argument or parameter."""
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services

        try:
            results = code_finder.find_functions_by_argument(argument, file)
            if not results:
                main_module.console.print(
                    f"[yellow]No functions found with argument '{argument}'[/yellow]"
                )
                return

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Function", style="cyan")
            table.add_column("Location", style="dim", overflow="fold")

            for item in results:
                path = item.get("path", "") or ""
                line_str = str(item.get("line_number", ""))
                location_str = f"{path}:{line_str}" if line_str else path
                table.add_row(item.get("function_name", ""), location_str)

            main_module.console.print(
                f"[cyan]Found {len(results)} function(s) with argument '{argument}':[/cyan]"
            )
            main_module.console.print(table)
        finally:
            db_manager.close_driver()
