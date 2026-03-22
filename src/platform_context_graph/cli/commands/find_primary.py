"""Primary find command registration for the CLI entrypoint."""

from __future__ import annotations

from typing import Any

import typer
from rich import box
from rich.table import Table

from ..visualizer import check_visual_flag, visualize_search_results


def register_find_primary_commands(main_module: Any, app: typer.Typer) -> typer.Typer:
    """Register the primary ``pcg find`` commands.

    Args:
        main_module: The imported ``platform_context_graph.cli.main`` module.
        app: The root Typer application.

    Returns:
        The shared ``find`` Typer sub-application.
    """
    find_app = typer.Typer(help="Find and search code elements")
    app.add_typer(find_app, name="find")

    @find_app.command("name")
    def find_by_name(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Exact name to search for"),
        type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type (function, class, file, module)",
        ),
        visual: bool = typer.Option(
            False,
            "--visual",
            "--viz",
            "-V",
            help="Show results as interactive graph visualization",
        ),
    ) -> None:
        """Find code elements by exact name."""
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services

        try:
            results: list[dict[str, object]] = []
            if type is None or type.lower() == "all":
                funcs = code_finder.find_by_function_name(name, fuzzy_search=False)
                classes = code_finder.find_by_class_name(name, fuzzy_search=False)
                variables = code_finder.find_by_variable_name(name)
                modules = code_finder.find_by_module_name(name)
                imports = code_finder.find_imports(name)

                for item in funcs:
                    item["type"] = "Function"
                for item in classes:
                    item["type"] = "Class"
                for item in variables:
                    item["type"] = "Variable"
                for item in modules:
                    item["type"] = "Module"
                    item["path"] = item.get("name", "External")
                for item in imports:
                    item["type"] = "Import"
                    item["name"] = item.get("alias") or item.get("imported_name")

                results.extend(funcs)
                results.extend(classes)
                results.extend(variables)
                results.extend(modules)
                results.extend(imports)
            elif type.lower() == "function":
                results = code_finder.find_by_function_name(name, fuzzy_search=False)
                for item in results:
                    item["type"] = "Function"
            elif type.lower() == "class":
                results = code_finder.find_by_class_name(name, fuzzy_search=False)
                for item in results:
                    item["type"] = "Class"
            elif type.lower() == "variable":
                results = code_finder.find_by_variable_name(name)
                for item in results:
                    item["type"] = "Variable"
            elif type.lower() == "module":
                results = code_finder.find_by_module_name(name)
                for item in results:
                    item["type"] = "Module"
                    item["path"] = item.get("name")
            elif type.lower() == "file":
                with db_manager.get_driver().session() as session:
                    result = session.run(
                        "MATCH (n:File) WHERE n.name = $name "
                        "RETURN n.name as name, n.path as path, "
                        "n.is_dependency as is_dependency",
                        name=name,
                    )
                    results = [dict(record) for record in result]
                    for item in results:
                        item["type"] = "File"

            if not results:
                main_module.console.print(
                    f"[yellow]No code elements found with name '{name}'[/yellow]"
                )
                return

            if check_visual_flag(ctx, visual):
                visualize_search_results(results, name, search_type="name")
                return

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="bold blue")
            table.add_column("Location", style="dim", overflow="fold")

            for item in results:
                path = item.get("path", "") or ""
                line_str = str(item.get("line_number", ""))
                location_str = f"{path}:{line_str}" if line_str else path
                table.add_row(
                    item.get("name", ""), item.get("type", "Unknown"), location_str
                )

            main_module.console.print(
                f"[cyan]Found {len(results)} matches for '{name}':[/cyan]"
            )
            main_module.console.print(table)
        finally:
            db_manager.close_driver()

    @find_app.command("pattern")
    def find_by_pattern(
        ctx: typer.Context,
        pattern: str = typer.Argument(
            ..., help="Substring pattern to search (fuzzy search fallback)"
        ),
        case_sensitive: bool = typer.Option(
            False, "--case-sensitive", "-c", help="Case-sensitive search"
        ),
        visual: bool = typer.Option(
            False,
            "--visual",
            "--viz",
            "-V",
            help="Show results as interactive graph visualization",
        ),
    ) -> None:
        """Find code elements using substring matching."""
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, _ = services

        try:
            with db_manager.get_driver().session() as session:
                if not case_sensitive:
                    query = """
                        MATCH (n)
                        WHERE (n:Function OR n:Class OR n:Module OR n:Variable) AND toLower(n.name) CONTAINS toLower($pattern)
                        RETURN
                            labels(n)[0] as type,
                            n.name as name,
                            n.path as path,
                            n.line_number as line_number,
                            n.is_dependency as is_dependency
                        ORDER BY n.is_dependency ASC, n.name
                        LIMIT 50
                    """
                else:
                    query = """
                        MATCH (n)
                        WHERE (n:Function OR n:Class OR n:Module OR n:Variable) AND n.name CONTAINS $pattern
                        RETURN
                            labels(n)[0] as type,
                            n.name as name,
                            n.path as path,
                            n.line_number as line_number,
                            n.is_dependency as is_dependency
                        ORDER BY n.is_dependency ASC, n.name
                        LIMIT 50
                    """
                result = session.run(query, pattern=pattern)
                results = [dict(record) for record in result]

            if not results:
                main_module.console.print(
                    f"[yellow]No matches found for pattern '{pattern}'[/yellow]"
                )
                return

            if check_visual_flag(ctx, visual):
                visualize_search_results(results, pattern, search_type="pattern")
                return

            if not case_sensitive and any(char in pattern for char in "*?["):
                main_module.console.print(
                    "[yellow]Note: Wildcards/Regex are not fully supported in this mode. Performing substring search.[/yellow]"
                )

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="blue")
            table.add_column("Location", style="dim", overflow="fold")
            table.add_column("Source", style="yellow")

            for item in results:
                path = item.get("path", "") or ""
                line_value = item.get("line_number", "")
                line_str = str(line_value if line_value is not None else "")
                location_str = f"{path}:{line_str}" if line_str else path
                table.add_row(
                    item.get("name", ""),
                    item.get("type", "Unknown"),
                    location_str,
                    "📦 Dependency" if item.get("is_dependency") else "📝 Project",
                )

            main_module.console.print(
                f"[cyan]Found {len(results)} matches for pattern '{pattern}':[/cyan]"
            )
            main_module.console.print(table)
        finally:
            db_manager.close_driver()

    @find_app.command("type")
    def find_by_type(
        ctx: typer.Context,
        element_type: str = typer.Argument(
            ..., help="Type to search for (function, class, file, module)"
        ),
        limit: int = typer.Option(
            50, "--limit", "-l", help="Maximum results to return"
        ),
        visual: bool = typer.Option(
            False,
            "--visual",
            "--viz",
            "-V",
            help="Show results as interactive graph visualization",
        ),
    ) -> None:
        """Find all elements of a specific type."""
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services

        try:
            results = code_finder.find_by_type(element_type, limit)
            if not results:
                main_module.console.print(
                    f"[yellow]No elements found of type '{element_type}'[/yellow]"
                )
                return

            for item in results:
                item["type"] = element_type.capitalize()

            if check_visual_flag(ctx, visual):
                visualize_search_results(results, element_type, search_type="type")
                return

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Name", style="cyan")
            table.add_column("Location", style="dim", overflow="fold")
            table.add_column("Source", style="yellow")

            for item in results:
                path = item.get("path", "") or ""
                line_str = str(item.get("line_number", ""))
                location_str = f"{path}:{line_str}" if line_str else path
                table.add_row(
                    item.get("name", ""),
                    location_str,
                    "📦 Dependency" if item.get("is_dependency") else "📝 Project",
                )

            main_module.console.print(
                f"[cyan]Found {len(results)} {element_type}s:[/cyan]"
            )
            main_module.console.print(table)
        finally:
            db_manager.close_driver()

    return find_app
