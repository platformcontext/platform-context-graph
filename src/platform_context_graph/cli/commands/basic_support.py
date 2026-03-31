"""Helpers for the root CLI command registrations."""

from __future__ import annotations

import shutil
from typing import Any

import typer
from rich.table import Table


def run_doctor(main_module: Any) -> None:
    """Run the CLI diagnostic checks and print the result summary."""
    main_module.console.print(
        "[bold cyan]🏥 Running PlatformContextGraph Diagnostics...[/bold cyan]\n"
    )

    all_checks_passed = True
    config: dict[str, Any] = {}

    main_module.console.print("[bold]1. Checking Configuration...[/bold]")
    try:
        config = main_module.config_manager.load_config()
        if main_module.config_manager.CONFIG_FILE.exists():
            main_module.console.print(
                "   [green]✓[/green] Configuration loaded from "
                f"{main_module.config_manager.CONFIG_FILE}"
            )
        else:
            main_module.console.print(
                "   [yellow]ℹ[/yellow] No config file found, using defaults"
            )
            main_module.console.print(
                "   [dim]Config will be created at: "
                f"{main_module.config_manager.CONFIG_FILE}[/dim]"
            )

        invalid_configs: list[str] = []
        for key, value in config.items():
            is_valid, error_msg = main_module.config_manager.validate_config_value(
                key, value
            )
            if not is_valid:
                invalid_configs.append(f"{key}: {error_msg}")

        if invalid_configs:
            main_module.console.print(
                "   [red]✗[/red] Invalid configuration values found:"
            )
            for error in invalid_configs:
                main_module.console.print(f"     - {error}")
            all_checks_passed = False
        else:
            main_module.console.print(
                "   [green]✓[/green] All configuration values are valid"
            )
    except Exception as exc:
        main_module.console.print(f"   [red]✗[/red] Configuration error: {exc}")
        all_checks_passed = False

    all_checks_passed = _run_database_check(
        main_module,
        config=config,
        all_checks_passed=all_checks_passed,
    )
    all_checks_passed = _run_tree_sitter_check(
        main_module,
        all_checks_passed=all_checks_passed,
    )
    all_checks_passed = _run_permissions_check(
        main_module,
        all_checks_passed=all_checks_passed,
    )

    main_module.console.print("\n[bold]5. Checking PCG Command...[/bold]")
    pcg_path = shutil.which("pcg")
    if pcg_path:
        main_module.console.print(f"   [green]✓[/green] pcg command found at: {pcg_path}")
    else:
        main_module.console.print(
            "   [yellow]⚠[/yellow] pcg command not in PATH (using python -m platform_context_graph)"
        )

    main_module.console.print("\n" + "=" * 60)
    if all_checks_passed:
        main_module.console.print(
            "[bold green]✅ All diagnostics passed! System is healthy.[/bold green]"
        )
    else:
        main_module.console.print(
            "[bold yellow]⚠️  Some issues detected. Please review the output above.[/bold yellow]"
        )
        main_module.console.print("\n[cyan]Common fixes:[/cyan]")
        main_module.console.print("  • For Neo4j issues: Run 'pcg neo4j setup'")
        main_module.console.print(
            "  • For missing packages: pip install platform-context-graph"
        )
        main_module.console.print("  • For config issues: Run 'pcg config reset'")
    main_module.console.print("=" * 60 + "\n")


def delete_all_repositories(main_module: Any) -> None:
    """Delete every indexed repository after explicit user confirmation."""
    services = main_module._initialize_services()
    if not all(services):
        return
    db_manager, graph_builder, code_finder = services

    try:
        repos = code_finder.list_indexed_repositories()
        if not repos:
            main_module.console.print("[yellow]No repositories to delete.[/yellow]")
            return

        _render_repository_delete_warning(main_module, repos)
        if not typer.confirm(
            "Are you sure you want to delete ALL repositories?", default=False
        ):
            main_module.console.print("[yellow]Deletion cancelled.[/yellow]")
            return

        main_module.console.print(
            "[yellow]Please type 'delete all' to confirm:[/yellow] ",
            end="",
        )
        if input().strip().lower() != "delete all":
            main_module.console.print(
                "[yellow]Deletion cancelled. Confirmation text did not match.[/yellow]"
            )
            return

        main_module.console.print("\n[cyan]Deleting all repositories...[/cyan]")
        deleted_count = 0
        for repo in repos:
            repo_path = repo.get("path", "")
            try:
                graph_builder.delete_repository_from_graph(repo_path)
                main_module.console.print(
                    f"[green]✓[/green] Deleted: {repo.get('name', '')}"
                )
                deleted_count += 1
            except Exception as exc:
                main_module.console.print(
                    f"[red]✗[/red] Failed to delete {repo.get('name', '')}: {exc}"
                )

        main_module.console.print(
            f"\n[bold green]Successfully deleted {deleted_count}/{len(repos)} repositories![/bold green]"
        )
    finally:
        db_manager.close_driver()


def _run_database_check(
    main_module: Any,
    *,
    config: dict[str, Any],
    all_checks_passed: bool,
) -> bool:
    """Run the CLI database diagnostics and preserve prior pass/fail state."""

    main_module.console.print("\n[bold]2. Checking Database Connection...[/bold]")
    try:
        main_module._load_credentials()
        default_db = config.get("DEFAULT_DATABASE", "falkordb")
        main_module.console.print(f"   Default database: {default_db}")

        if default_db == "neo4j":
            uri = main_module.os.environ.get("NEO4J_URI")
            username = main_module.os.environ.get("NEO4J_USERNAME")
            password = main_module.os.environ.get("NEO4J_PASSWORD")

            if uri and username and password:
                main_module.console.print(
                    f"   [cyan]Testing Neo4j connection to {uri}...[/cyan]"
                )
                is_connected, error_msg = main_module.DatabaseManager.test_connection(
                    uri,
                    username,
                    password,
                    database=main_module.os.environ.get("NEO4J_DATABASE"),
                )
                if is_connected:
                    main_module.console.print(
                        "   [green]✓[/green] Neo4j connection successful"
                    )
                else:
                    main_module.console.print(
                        "   [red]✗[/red] Neo4j connection failed: " f"{error_msg}"
                    )
                    return False
            else:
                main_module.console.print(
                    "   [yellow]⚠[/yellow] Neo4j credentials not set. Run 'pcg neo4j setup'"
                )
            return all_checks_passed

        try:
            import falkordb  # noqa: F401

            main_module.console.print("   [green]✓[/green] FalkorDB Lite is installed")
        except ImportError:
            main_module.console.print(
                "   [yellow]⚠[/yellow] FalkorDB Lite not installed (Python 3.12+ only)"
            )
            main_module.console.print("       Run: pip install falkordblite")
    except Exception as exc:
        main_module.console.print(f"   [red]✗[/red] Database check error: {exc}")
        return False
    return all_checks_passed


def _run_tree_sitter_check(main_module: Any, *, all_checks_passed: bool) -> bool:
    """Run the parser-installation diagnostics and preserve prior pass/fail state."""

    main_module.console.print("\n[bold]3. Checking Tree-Sitter Installation...[/bold]")
    try:
        from tree_sitter import Language, Parser  # noqa: F401

        main_module.console.print("   [green]✓[/green] tree-sitter is installed")

        try:
            from tree_sitter_language_pack import get_language

            main_module.console.print(
                "   [green]✓[/green] tree-sitter-language-pack is installed"
            )
            for language in ["python", "javascript", "typescript"]:
                try:
                    get_language(language)
                    main_module.console.print(
                        f"   [green]✓[/green] {language} parser available"
                    )
                except Exception:
                    main_module.console.print(
                        f"   [yellow]⚠[/yellow] {language} parser not available"
                    )
        except ImportError:
            main_module.console.print(
                "   [red]✗[/red] tree-sitter-language-pack not installed"
            )
            return False
    except ImportError as exc:
        main_module.console.print(f"   [red]✗[/red] tree-sitter not installed: {exc}")
        return False
    return all_checks_passed


def _run_permissions_check(main_module: Any, *, all_checks_passed: bool) -> bool:
    """Verify the CLI config directory exists and can be written when needed."""

    main_module.console.print("\n[bold]4. Checking File Permissions...[/bold]")
    try:
        config_dir = main_module.config_manager.CONFIG_DIR
        if config_dir.exists():
            main_module.console.print(
                f"   [green]✓[/green] Config directory exists: {config_dir}"
            )
            test_file = config_dir / ".test_write"
            try:
                test_file.touch()
                test_file.unlink()
                main_module.console.print(
                    "   [green]✓[/green] Config directory is writable"
                )
            except Exception as exc:
                main_module.console.print(
                    f"   [red]✗[/red] Config directory not writable: {exc}"
                )
                return False
        else:
            main_module.console.print(
                "   [yellow]⚠[/yellow] Config directory doesn't exist, will be created on first use"
            )
    except Exception as exc:
        main_module.console.print(f"   [red]✗[/red] Permission check error: {exc}")
        return False
    return all_checks_passed


def _render_repository_delete_warning(main_module: Any, repos: list[dict[str, Any]]) -> None:
    """Render the destructive-delete confirmation table for indexed repos."""

    main_module.console.print(
        f"\n[bold red]⚠️  WARNING: You are about to delete ALL {len(repos)} repositories![/bold red]\n"
    )
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="dim")
    for repo in repos:
        table.add_row(repo.get("name", ""), repo.get("path", ""))
    main_module.console.print(table)
    main_module.console.print()
