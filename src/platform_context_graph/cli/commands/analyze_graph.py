"""Graph-oriented analyze command registration for the CLI entrypoint."""

from __future__ import annotations

from typing import Any

import typer
from rich import box
from rich.table import Table

from ..remote import remote_mode_requested
from ..remote_commands import render_remote_relationship_query
from ..visualizer import (
    check_visual_flag,
    visualize_call_chain,
    visualize_call_graph,
    visualize_dependencies,
    visualize_inheritance_tree,
)
def register_analyze_graph_commands(main_module: Any, app: typer.Typer) -> typer.Typer:
    """Register graph-oriented ``pcg analyze`` commands.

    Args:
        main_module: The imported ``platform_context_graph.cli.main`` module.
        app: The root Typer application.

    Returns:
        The shared ``analyze`` Typer sub-application.
    """
    analyze_app = typer.Typer(
        help="Analyze code relationships, dependencies, and quality"
    )
    app.add_typer(analyze_app, name="analyze")

    @analyze_app.command("calls")
    def analyze_calls(
        ctx: typer.Context,
        function: str = typer.Argument(..., help="Function name to analyze"),
        file: str | None = typer.Option(
            None, "--file", "-f", help="Specific file path"
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
        """Show what functions the target function calls."""
        if remote_mode_requested(service_url, profile):
            if check_visual_flag(ctx, visual):
                raise typer.BadParameter(
                    "Remote analyze commands do not support --visual in v1."
                )
            render_remote_relationship_query(
                main_module,
                query_type="find_callees",
                target=function,
                context=file,
                service_url=service_url,
                api_key=api_key,
                profile=profile,
                failure_label="Remote analyze failed",
            )
            return
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services
        try:
            results = code_finder.what_does_function_call(function, file)
            if not results:
                main_module.console.print(
                    f"[yellow]No function calls found for '{function}'[/yellow]"
                )
                return

            if check_visual_flag(ctx, visual):
                visualize_call_graph(results, function, direction="outgoing")
                return

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Called Function", style="cyan")
            table.add_column("Location", style="dim", overflow="fold")
            table.add_column("Type", style="yellow")

            for result in results:
                path = result.get("called_file_path", "")
                line_str = str(result.get("called_line_number", ""))
                location_str = f"{path}:{line_str}" if line_str else path
                table.add_row(
                    result.get("called_function", ""),
                    location_str,
                    (
                        "📦 Dependency"
                        if result.get("called_is_dependency")
                        else "📝 Project"
                    ),
                )

            main_module.console.print(
                f"\n[bold cyan]Function '{function}' calls:[/bold cyan]"
            )
            main_module.console.print(table)
            main_module.console.print(f"\n[dim]Total: {len(results)} function(s)[/dim]")
        finally:
            db_manager.close_driver()

    @analyze_app.command("callers")
    def analyze_callers(
        ctx: typer.Context,
        function: str = typer.Argument(..., help="Function name to analyze"),
        file: str | None = typer.Option(
            None, "--file", "-f", help="Specific file path"
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
        """Show what functions call the target function."""
        if remote_mode_requested(service_url, profile):
            if check_visual_flag(ctx, visual):
                raise typer.BadParameter(
                    "Remote analyze commands do not support --visual in v1."
                )
            render_remote_relationship_query(
                main_module,
                query_type="find_callers",
                target=function,
                context=file,
                service_url=service_url,
                api_key=api_key,
                profile=profile,
                failure_label="Remote analyze failed",
            )
            return
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services
        try:
            results = code_finder.who_calls_function(function, file)
            if not results:
                main_module.console.print(
                    f"[yellow]No callers found for '{function}'[/yellow]"
                )
                return

            if check_visual_flag(ctx, visual):
                visualize_call_graph(results, function, direction="incoming")
                return

            table = Table(
                show_header=True, header_style="bold magenta", box=box.ROUNDED
            )
            table.add_column("Caller Function", style="cyan")
            table.add_column("Location", style="green")
            table.add_column("Call Type", style="yellow")

            for result in results:
                path = result.get("caller_file_path", "")
                line_number = result.get("caller_line_number")
                location = f"{path}:{line_number}" if line_number else path
                table.add_row(
                    result.get("caller_function", ""),
                    location,
                    (
                        "📦 Dependency"
                        if result.get("caller_is_dependency")
                        else "📝 Project"
                    ),
                )

            main_module.console.print(
                f"\n[bold cyan]Functions that call '{function}':[/bold cyan]"
            )
            main_module.console.print(table)
            main_module.console.print(f"\n[dim]Total: {len(results)} caller(s)[/dim]")
        finally:
            db_manager.close_driver()

    @analyze_app.command("chain")
    def analyze_chain(
        ctx: typer.Context,
        from_func: str = typer.Argument(..., help="Starting function"),
        to_func: str = typer.Argument(..., help="Target function"),
        max_depth: int = typer.Option(
            5, "--depth", "-d", help="Maximum call chain depth"
        ),
        from_file: str | None = typer.Option(
            None, "--from-file", help="File for starting function"
        ),
        to_file: str | None = typer.Option(
            None, "--to-file", help="File for target function"
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
        """Show the call chain between two functions."""
        if remote_mode_requested(service_url, profile):
            if check_visual_flag(ctx, visual):
                raise typer.BadParameter(
                    "Remote analyze commands do not support --visual in v1."
                )
            if from_file or to_file:
                raise typer.BadParameter(
                    "Remote analyze chain does not support --from-file or --to-file in v1."
                )
            render_remote_relationship_query(
                main_module,
                query_type="call_chain",
                target=f"{from_func}->{to_func}",
                context=str(max_depth),
                service_url=service_url,
                api_key=api_key,
                profile=profile,
                failure_label="Remote analyze chain failed",
            )
            return
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services
        try:
            results = code_finder.find_function_call_chain(
                from_func, to_func, max_depth, from_file, to_file
            )
            if not results:
                main_module.console.print(
                    f"[yellow]No call chain found between '{from_func}' and '{to_func}' within depth {max_depth}[/yellow]"
                )
                return

            if check_visual_flag(ctx, visual):
                visualize_call_chain(results, from_func, to_func)
                return

            for index, chain in enumerate(results, 1):
                main_module.console.print(
                    f"\n[bold cyan]Call Chain #{index} (length: {chain.get('chain_length', 0)}):[/bold cyan]"
                )
                functions = chain.get("function_chain", [])
                call_details = chain.get("call_details", [])

                for position, function_info in enumerate(functions):
                    indent = "  " * position
                    main_module.console.print(
                        f"{indent}[cyan]{function_info.get('name', 'Unknown')}[/cyan] "
                        f"[dim]({function_info.get('path', '')}:{function_info.get('line_number', '')})[/dim]"
                    )

                    if position < len(functions) - 1 and position < len(call_details):
                        detail = call_details[position]
                        line = detail.get("call_line", "?")
                        args_value = detail.get("args", [])
                        args_info = ""
                        if args_value:
                            if isinstance(args_value, list):
                                clean_args = [
                                    str(arg)
                                    for arg in args_value
                                    if str(arg) not in ("(", ")", ",")
                                ]
                                args_str = ", ".join(clean_args)
                            else:
                                args_str = str(args_value)
                            if len(args_str) > 50:
                                args_str = args_str[:47] + "..."
                            args_info = f" [dim]({args_str})[/dim]"

                        main_module.console.print(
                            f"{indent}  ⬇ [dim]calls at line {line}[/dim]{args_info}"
                        )
        finally:
            db_manager.close_driver()

    @analyze_app.command("deps")
    def analyze_dependencies(
        ctx: typer.Context,
        target: str = typer.Argument(..., help="Module name"),
        show_external: bool = typer.Option(
            True, "--external/--no-external", help="Show external dependencies"
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
        """Show dependencies and importers for a module."""
        del show_external
        if remote_mode_requested(service_url, profile):
            if check_visual_flag(ctx, visual):
                raise typer.BadParameter(
                    "Remote analyze commands do not support --visual in v1."
                )
            render_remote_relationship_query(
                main_module,
                query_type="module_deps",
                target=target,
                context=None,
                service_url=service_url,
                api_key=api_key,
                profile=profile,
                failure_label="Remote analyze deps failed",
            )
            return
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services
        try:
            results = code_finder.find_module_dependencies(target)
            if not results.get("importers") and not results.get("imports"):
                main_module.console.print(
                    f"[yellow]No dependency information found for '{target}'[/yellow]"
                )
                return

            if check_visual_flag(ctx, visual):
                visualize_dependencies(results, target)
                return

            if results.get("importers"):
                main_module.console.print(
                    f"\n[bold cyan]Files that import '{target}':[/bold cyan]"
                )
                table = Table(
                    show_header=True, header_style="bold magenta", box=box.ROUNDED
                )
                table.add_column("Location", style="cyan", overflow="fold")

                for importer in results["importers"]:
                    path = importer.get("importer_file_path", "")
                    line_str = str(importer.get("import_line_number", ""))
                    location_str = f"{path}:{line_str}" if line_str else path
                    table.add_row(location_str)
                main_module.console.print(table)
        finally:
            db_manager.close_driver()

    @analyze_app.command("tree")
    def analyze_inheritance_tree(
        ctx: typer.Context,
        class_name: str = typer.Argument(..., help="Class name"),
        file: str | None = typer.Option(
            None, "--file", "-f", help="Specific file path"
        ),
        visual: bool = typer.Option(
            False,
            "--visual",
            "--viz",
            "-V",
            help="Show results as interactive graph visualization",
        ),
    ) -> None:
        """Show inheritance hierarchy for a class."""
        main_module._load_credentials()
        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, code_finder = services

        try:
            results = code_finder.find_class_hierarchy(class_name, file)
            has_hierarchy = results.get("parent_classes") or results.get(
                "child_classes"
            )
            if check_visual_flag(ctx, visual):
                if has_hierarchy:
                    visualize_inheritance_tree(results, class_name)
                else:
                    main_module.console.print(
                        f"[yellow]No inheritance hierarchy to visualize for '{class_name}'[/yellow]"
                    )
                return

            main_module.console.print(
                f"\n[bold cyan]Class Hierarchy for '{class_name}':[/bold cyan]\n"
            )
            if results.get("parent_classes"):
                main_module.console.print(
                    "[bold yellow]Parents (inherits from):[/bold yellow]"
                )
                for parent in results["parent_classes"]:
                    main_module.console.print(
                        f"  ⬆ [cyan]{parent.get('parent_class', '')}[/cyan] "
                        f"[dim]({parent.get('parent_file_path', '')}:{parent.get('parent_line_number', '')})[/dim]"
                    )
            else:
                main_module.console.print("[dim]No parent classes found[/dim]")

            main_module.console.print()
            if results.get("child_classes"):
                main_module.console.print(
                    "[bold yellow]Children (classes that inherit from this):[/bold yellow]"
                )
                for child in results["child_classes"]:
                    main_module.console.print(
                        f"  ⬇ [cyan]{child.get('child_class', '')}[/cyan] "
                        f"[dim]({child.get('child_file_path', '')}:{child.get('child_line_number', '')})[/dim]"
                    )
            else:
                main_module.console.print("[dim]No child classes found[/dim]")

            main_module.console.print()
            if results.get("methods"):
                main_module.console.print(
                    f"[bold yellow]Methods ({len(results['methods'])}):[/bold yellow]"
                )
                for method in results["methods"][:10]:
                    main_module.console.print(
                        f"  • [green]{method.get('method_name', '')}[/green]({method.get('method_args', '')})"
                    )
                if len(results["methods"]) > 10:
                    main_module.console.print(
                        f"  [dim]... and {len(results['methods']) - 10} more[/dim]"
                    )
        finally:
            db_manager.close_driver()

    return analyze_app
