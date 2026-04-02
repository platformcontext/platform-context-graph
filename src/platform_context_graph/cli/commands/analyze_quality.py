"""Quality-oriented analyze command registration for the CLI entrypoint."""

from __future__ import annotations

from typing import Any

import typer
from rich import box
from rich.table import Table

from ..remote import remote_mode_requested
from ..remote_commands import (
    render_remote_complexity,
    render_remote_dead_code,
    render_remote_relationship_query,
)
from ..visualizer import check_visual_flag, visualize_overrides


def register_analyze_quality_commands(
    main_module: Any, analyze_app: typer.Typer
) -> None:
    """Register quality-oriented ``pcg analyze`` commands.

    Args:
        main_module: The imported ``platform_context_graph.cli.main`` module.
        analyze_app: The shared ``analyze`` Typer sub-application.
    """

    @analyze_app.command("complexity")
    def analyze_complexity(
        path: str | None = typer.Argument(
            None, help="Specific function name to analyze"
        ),
        threshold: int = typer.Option(
            10, "--threshold", "-t", help="Complexity threshold for warnings"
        ),
        limit: int = typer.Option(20, "--limit", "-l", help="Maximum results to show"),
        file: str | None = typer.Option(
            None,
            "--file",
            "-f",
            help="Specific file path (only used when function name is provided)",
        ),
        service_url: str | None = typer.Option(
            None,
            "--service-url",
            help="Base URL of the remote PlatformContextGraph HTTP service.",
        ),
        api_key: str | None = typer.Option(
            None,
            "--api-key",
            help="Bearer token for the remote PlatformContextGraph HTTP service.",
        ),
        profile: str | None = typer.Option(
            None,
            "--profile",
            help="Named remote profile used to resolve service URL and token.",
        ),
    ) -> None:
        """Show cyclomatic complexity for functions."""
        if remote_mode_requested(service_url, profile):
            render_remote_complexity(
                main_module,
                function_name=path,
                path=file,
                limit=limit,
                service_url=service_url,
                api_key=api_key,
                profile=profile,
            )
            return
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services

        try:
            if path:
                result = code_finder.get_cyclomatic_complexity(path, file)
                if result:
                    main_module.console.print(
                        f"\n[bold cyan]Complexity for '{path}':[/bold cyan]"
                    )
                    main_module.console.print(
                        "  Cyclomatic Complexity: "
                        f"[yellow]{result.get('complexity', 'N/A')}[/yellow]"
                    )
                    main_module.console.print(
                        f"  File: [dim]{result.get('path', '')}[/dim]"
                    )
                    main_module.console.print(
                        f"  Line: [dim]{result.get('line_number', '')}[/dim]"
                    )
                else:
                    main_module.console.print(
                        f"[yellow]Function '{path}' not found or has no complexity data[/yellow]"
                    )
                return

            results = code_finder.find_most_complex_functions(limit)
            if not results:
                main_module.console.print(
                    "[yellow]No complexity data available[/yellow]"
                )
                return

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Function", style="cyan")
            table.add_column("Complexity", style="yellow", justify="right")
            table.add_column("Location", style="dim", overflow="fold")

            for function_info in results:
                complexity = function_info.get("complexity", 0)
                color = (
                    "red"
                    if complexity > threshold
                    else "yellow" if complexity > threshold / 2 else "green"
                )
                function_path = function_info.get("path", "")
                line_str = str(function_info.get("line_number", ""))
                location_str = (
                    f"{function_path}:{line_str}" if line_str else function_path
                )
                table.add_row(
                    function_info.get("function_name", ""),
                    f"[{color}]{complexity}[/{color}]",
                    location_str,
                )

            main_module.console.print(
                f"\n[bold cyan]Most Complex Functions (threshold: {threshold}):[/bold cyan]"
            )
            main_module.console.print(table)
            main_module.console.print(
                f"\n[dim]{len([item for item in results if item.get('complexity', 0) > threshold])} function(s) exceed threshold[/dim]"
            )
        finally:
            db_manager.close_driver()

    @analyze_app.command("dead-code")
    def analyze_dead_code(
        path: str | None = typer.Argument(
            None, help="Path to analyze (not yet implemented)"
        ),
        exclude_decorators: str | None = typer.Option(
            None, "--exclude", "-e", help="Comma-separated decorators to exclude"
        ),
        service_url: str | None = typer.Option(
            None,
            "--service-url",
            help="Base URL of the remote PlatformContextGraph HTTP service.",
        ),
        api_key: str | None = typer.Option(
            None,
            "--api-key",
            help="Bearer token for the remote PlatformContextGraph HTTP service.",
        ),
        profile: str | None = typer.Option(
            None,
            "--profile",
            help="Named remote profile used to resolve service URL and token.",
        ),
    ) -> None:
        """Find potentially unused functions and classes."""
        del path
        if remote_mode_requested(service_url, profile):
            render_remote_dead_code(
                main_module,
                exclude_decorated_with=(
                    exclude_decorators.split(",") if exclude_decorators else None
                ),
                service_url=service_url,
                api_key=api_key,
                profile=profile,
            )
            return
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services

        try:
            exclude_list = exclude_decorators.split(",") if exclude_decorators else []
            results = code_finder.find_dead_code(exclude_list)
            unused_funcs = results.get("potentially_unused_functions", [])
            if not unused_funcs:
                main_module.console.print("[green]✓ No dead code found![/green]")
                return

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Function", style="cyan")
            table.add_column("Location", style="dim", overflow="fold")

            for function_info in unused_funcs:
                function_path = function_info.get("path", "")
                line_str = str(function_info.get("line_number", ""))
                location_str = (
                    f"{function_path}:{line_str}" if line_str else function_path
                )
                table.add_row(function_info.get("function_name", ""), location_str)

            main_module.console.print(
                "\n[bold yellow]⚠️  Potentially Unused Functions:[/bold yellow]"
            )
            main_module.console.print(table)
            main_module.console.print(
                f"\n[dim]Total: {len(unused_funcs)} function(s)[/dim]"
            )
            main_module.console.print(f"[dim]Note: {results.get('note', '')}[/dim]")
        finally:
            db_manager.close_driver()

    @analyze_app.command("overrides")
    def analyze_overrides(
        ctx: typer.Context,
        function_name: str = typer.Argument(
            ..., help="Function/method name to find implementations of"
        ),
        visual: bool = typer.Option(
            False,
            "--visual",
            "--viz",
            "-V",
            help="Show results as interactive graph visualization",
        ),
        service_url: str | None = typer.Option(
            None,
            "--service-url",
            help="Base URL of the remote PlatformContextGraph HTTP service.",
        ),
        api_key: str | None = typer.Option(
            None,
            "--api-key",
            help="Bearer token for the remote PlatformContextGraph HTTP service.",
        ),
        profile: str | None = typer.Option(
            None,
            "--profile",
            help="Named remote profile used to resolve service URL and token.",
        ),
    ) -> None:
        """Find all implementations of a function across different classes."""
        if remote_mode_requested(service_url, profile):
            if check_visual_flag(ctx, visual):
                raise typer.BadParameter(
                    "Remote analyze commands do not support --visual in v1."
                )
            render_remote_relationship_query(
                main_module,
                query_type="overrides",
                target=function_name,
                context=None,
                service_url=service_url,
                api_key=api_key,
                profile=profile,
                failure_label="Remote overrides analysis failed",
            )
            return
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services

        try:
            results = code_finder.find_function_overrides(function_name)
            if not results:
                main_module.console.print(
                    f"[yellow]No implementations found for function '{function_name}'[/yellow]"
                )
                return

            if check_visual_flag(ctx, visual):
                visualize_overrides(results, function_name)
                return

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Class", style="cyan")
            table.add_column("Function", style="green")
            table.add_column("Location", style="dim", overflow="fold")

            for item in results:
                path = item.get("class_file_path", "")
                line_str = str(item.get("function_line_number", ""))
                location_str = f"{path}:{line_str}" if line_str else path
                table.add_row(
                    item.get("class_name", ""),
                    item.get("function_name", ""),
                    location_str,
                )

            main_module.console.print(
                f"\n[bold cyan]Found {len(results)} implementation(s) of '{function_name}':[/bold cyan]"
            )
            main_module.console.print(table)
        finally:
            db_manager.close_driver()

    @analyze_app.command("variable")
    def analyze_variable_usage(
        variable_name: str = typer.Argument(..., help="Variable name to analyze"),
        file: str | None = typer.Option(
            None, "--file", "-f", help="Specific file path"
        ),
        service_url: str | None = typer.Option(
            None,
            "--service-url",
            help="Base URL of the remote PlatformContextGraph HTTP service.",
        ),
        api_key: str | None = typer.Option(
            None,
            "--api-key",
            help="Bearer token for the remote PlatformContextGraph HTTP service.",
        ),
        profile: str | None = typer.Option(
            None,
            "--profile",
            help="Named remote profile used to resolve service URL and token.",
        ),
    ) -> None:
        """Analyze where a variable is defined and used across the codebase."""
        if remote_mode_requested(service_url, profile):
            render_remote_relationship_query(
                main_module,
                query_type="variable_scope",
                target=variable_name,
                context=file,
                service_url=service_url,
                api_key=api_key,
                profile=profile,
                failure_label="Remote variable analysis failed",
            )
            return
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services

        try:
            scope_results = code_finder.find_variable_usage_scope(variable_name, file)
            instances = scope_results.get("instances", [])
            if not instances:
                main_module.console.print(
                    f"[yellow]No instances found for variable '{variable_name}'[/yellow]"
                )
                return

            main_module.console.print(
                f"\n[bold cyan]Variable '{variable_name}' Usage Analysis:[/bold cyan]\n"
            )

            by_scope: dict[str, list[dict[str, object]]] = {}
            for instance in instances:
                scope_type = instance.get("scope_type", "unknown")
                by_scope.setdefault(scope_type, []).append(instance)

            for scope_type, items in by_scope.items():
                main_module.console.print(
                    f"[bold yellow]{scope_type.upper()} Scope ({len(items)} instance(s)):[/bold yellow]"
                )
                table = Table(
                    show_header=True, header_style="bold magenta", box=box.ROUNDED
                )
                table.add_column("Scope Name", style="cyan")
                table.add_column("Location", style="dim", overflow="fold")
                table.add_column("Value", style="yellow")

                for item in items:
                    path = item.get("path", "")
                    line_str = str(item.get("line_number", ""))
                    location_str = f"{path}:{line_str}" if line_str else path
                    table.add_row(
                        item.get("scope_name", ""),
                        location_str,
                        (
                            str(item.get("variable_value", ""))[:50]
                            if item.get("variable_value")
                            else "-"
                        ),
                    )

                main_module.console.print(table)
                main_module.console.print()

            main_module.console.print(
                f"[dim]Total: {len(instances)} instance(s) across {len(by_scope)} scope type(s)[/dim]"
            )
        finally:
            db_manager.close_driver()
