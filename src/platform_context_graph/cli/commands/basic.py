"""Core non-grouped command registration for the CLI entrypoint."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import typer
from rich import box
from rich.table import Table

from ..visualizer import check_visual_flag


def register_basic_commands(main_module: Any, app: typer.Typer) -> None:
    """Register the core CLI commands on the root Typer app.

    Args:
        main_module: The imported ``platform_context_graph.cli.main`` module.
        app: The root Typer application.
    """

    @app.command()
    def doctor() -> None:
        """Run diagnostics to check system health and configuration."""
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
                    is_connected, error_msg = (
                        main_module.DatabaseManager.test_connection(
                            uri,
                            username,
                            password,
                            database=main_module.os.environ.get("NEO4J_DATABASE"),
                        )
                    )
                    if is_connected:
                        main_module.console.print(
                            "   [green]✓[/green] Neo4j connection successful"
                        )
                    else:
                        main_module.console.print(
                            "   [red]✗[/red] Neo4j connection failed: " f"{error_msg}"
                        )
                        all_checks_passed = False
                else:
                    main_module.console.print(
                        "   [yellow]⚠[/yellow] Neo4j credentials not set. Run 'pcg neo4j setup'"
                    )
            else:
                try:
                    import falkordb  # noqa: F401

                    main_module.console.print(
                        "   [green]✓[/green] FalkorDB Lite is installed"
                    )
                except ImportError:
                    main_module.console.print(
                        "   [yellow]⚠[/yellow] FalkorDB Lite not installed (Python 3.12+ only)"
                    )
                    main_module.console.print("       Run: pip install falkordblite")
        except Exception as exc:
            main_module.console.print(f"   [red]✗[/red] Database check error: {exc}")
            all_checks_passed = False

        main_module.console.print(
            "\n[bold]3. Checking Tree-Sitter Installation...[/bold]"
        )
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
                all_checks_passed = False
        except ImportError as exc:
            main_module.console.print(
                f"   [red]✗[/red] tree-sitter not installed: {exc}"
            )
            all_checks_passed = False

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
                    all_checks_passed = False
            else:
                main_module.console.print(
                    "   [yellow]⚠[/yellow] Config directory doesn't exist, will be created on first use"
                )
        except Exception as exc:
            main_module.console.print(f"   [red]✗[/red] Permission check error: {exc}")
            all_checks_passed = False

        main_module.console.print("\n[bold]5. Checking PCG Command...[/bold]")
        pcg_path = shutil.which("pcg")
        if pcg_path:
            main_module.console.print(
                f"   [green]✓[/green] pcg command found at: {pcg_path}"
            )
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

    @app.command()
    def index(
        path: str | None = typer.Argument(
            None,
            help=(
                "Local filesystem path to index. Defaults to the current directory. "
                "Use 'pcg workspace ...' for the canonical shared workspace source model."
            ),
        ),
        force: bool = typer.Option(
            False, "--force", "-f", help="Force re-index (delete existing and rebuild)"
        ),
    ) -> None:
        """Index a local filesystem path into the code graph."""
        main_module._load_credentials()
        target_path = path or str(Path.cwd())
        if force:
            main_module.console.print(
                "[yellow]Force re-indexing (--force flag detected)[/yellow]"
            )
            main_module.reindex_helper(target_path)
        else:
            main_module.index_helper(target_path)

    @app.command(name="index-status")
    def index_status(
        target: str | None = typer.Argument(
            None,
            help="Repository/workspace path or checkpoint run ID. Defaults to the current directory.",
        )
    ) -> None:
        """Show the latest checkpointed indexing status for a path or run ID."""

        main_module.index_status_helper(target)

    @app.command()
    def finalize(
        stages: list[str] | None = typer.Option(
            None,
            "--stage",
            "-s",
            help="Specific stages to run (can repeat). Defaults to graph-only stages.",
        ),
        run_id: str | None = typer.Option(
            None,
            "--run-id",
            help="Run ID to load snapshots from (enables file-dependent stages).",
        ),
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="Show what would run without executing.",
        ),
    ) -> None:
        """Re-run finalization stages against an existing graph.

        Use after a failed finalization or on a restored database backup.
        Without --run-id, runs graph-only stages (workloads, relationship_resolution).
        With --run-id, also runs file-dependent stages if NDJSON snapshots exist.
        """

        main_module._load_credentials()
        main_module.finalize_helper(
            stages=stages,
            run_id=run_id,
            dry_run=dry_run,
        )

    @app.command()
    def clean() -> None:
        """Remove orphaned nodes and relationships from the database."""
        main_module._load_credentials()
        main_module.clean_helper()

    @app.command()
    def stats(
        path: str | None = typer.Argument(
            None, help="Path to show stats for. Omit for overall stats."
        )
    ) -> None:
        """Show indexing statistics."""
        main_module._load_credentials()
        normalized_path = str(Path(path).resolve()) if path else None
        main_module.stats_helper(normalized_path)

    @app.command()
    def delete(
        path: str | None = typer.Argument(
            None, help="Path of the repository to delete from the code graph."
        ),
        all_repos: bool = typer.Option(
            False, "--all", help="Delete all indexed repositories"
        ),
    ) -> None:
        """Delete one repository or every indexed repository."""
        main_module._load_credentials()

        if not all_repos:
            if not path:
                main_module.console.print(
                    "[red]Error: Please provide a path or use --all to delete all repositories[/red]"
                )
                main_module.console.print(
                    "Usage: pcg delete <path> or pcg delete --all"
                )
                raise typer.Exit(code=1)
            main_module.delete_helper(path)
            return

        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, graph_builder, code_finder = services

        try:
            repos = code_finder.list_indexed_repositories()
            if not repos:
                main_module.console.print("[yellow]No repositories to delete.[/yellow]")
                return

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

            if not typer.confirm(
                "Are you sure you want to delete ALL repositories?", default=False
            ):
                main_module.console.print("[yellow]Deletion cancelled.[/yellow]")
                return

            main_module.console.print(
                "[yellow]Please type 'delete all' to confirm:[/yellow] ", end=""
            )
            confirmation = input()
            if confirmation.strip().lower() != "delete all":
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

    @app.command()
    def visualize(
        repo: str | None = typer.Option(
            None, "--repo", "-r", help="Path to the repository to visualize."
        ),
        port: int = typer.Option(
            8000, "--port", "-p", help="Port to run the visualizer server on."
        ),
    ) -> None:
        """Launch the interactive Playground UI for the code graph."""
        main_module._load_credentials()
        main_module.visualize_helper(repo, port)

    @app.command("list")
    def list_repositories() -> None:
        """List all indexed repositories."""
        main_module._load_credentials()
        main_module.list_repos_helper()

    @app.command(name="add-package")
    def add_package(
        package_name: str = typer.Argument(..., help="Name of the package to add."),
        language: str = typer.Argument(..., help="Language of the package."),
    ) -> None:
        """Add a package dependency to the code graph."""
        main_module._load_credentials()
        main_module.add_package_helper(package_name, language)

    @app.command()
    def watch(
        path: str = typer.Argument(
            ".",
            help=(
                "Local filesystem path to watch. Defaults to current directory. "
                "Use 'pcg workspace ...' for shared workspace discovery and sync."
            ),
        ),
        scope: str = typer.Option(
            "auto",
            "--scope",
            help="Watch scope: auto, repo, or workspace.",
        ),
        include_repo: list[str] | None = typer.Option(
            None,
            "--include-repo",
            help="Repository glob(s) to include when watching a workspace.",
        ),
        exclude_repo: list[str] | None = typer.Option(
            None,
            "--exclude-repo",
            help="Repository glob(s) to exclude when watching a workspace.",
        ),
    ) -> None:
        """Watch a local filesystem path for changes and update the graph automatically."""
        main_module._load_credentials()
        main_module.watch_helper(
            path,
            scope=scope,
            include_repositories=include_repo,
            exclude_repositories=exclude_repo,
        )

    @app.command()
    def unwatch(path: str = typer.Argument(..., help="Path to stop watching")) -> None:
        """Stop watching a directory for changes."""
        main_module._load_credentials()
        main_module.unwatch_helper(path)

    @app.command()
    def watching() -> None:
        """List all directories currently being watched for changes."""
        main_module._load_credentials()
        main_module.list_watching_helper()

    @app.command("query")
    def query_graph(
        ctx: typer.Context,
        query: str = typer.Argument(..., help="Cypher query to execute (read-only)"),
        visual: bool = typer.Option(
            False,
            "--visual",
            "--viz",
            "-V",
            help="Show results as interactive graph visualization",
        ),
    ) -> None:
        """Execute a custom Cypher query on the code graph."""
        main_module._load_credentials()
        if check_visual_flag(ctx, visual):
            main_module.cypher_helper_visual(query)
        else:
            main_module.cypher_helper(query)

    @app.command("cypher", hidden=True)
    def cypher_legacy(
        query: str = typer.Argument(..., help="The read-only Cypher query to execute.")
    ) -> None:
        """Run the deprecated ``pcg cypher`` alias."""
        main_module.console.print(
            "[yellow]⚠️  'pcg cypher' is deprecated. Use 'pcg query' instead.[/yellow]"
        )
        main_module.cypher_helper(query)

    @app.command("i", rich_help_panel="Shortcuts")
    def index_abbrev(
        path: str | None = typer.Argument(None, help="Path to index"),
        force: bool = typer.Option(
            False, "--force", "-f", help="Force re-index (delete existing and rebuild)"
        ),
    ) -> None:
        """Run the ``pcg index`` shortcut."""
        index(path, force=force)

    @app.command("ls", rich_help_panel="Shortcuts")
    def list_abbrev() -> None:
        """Run the ``pcg list`` shortcut."""
        list_repositories()

    @app.command("rm", rich_help_panel="Shortcuts")
    def delete_abbrev(
        path: str | None = typer.Argument(None, help="Path to delete"),
        all_repos: bool = typer.Option(
            False, "--all", help="Delete all indexed repositories"
        ),
    ) -> None:
        """Run the ``pcg delete`` shortcut."""
        delete(path, all_repos)

    @app.command("v", rich_help_panel="Shortcuts")
    def visualize_abbrev(
        repo: str | None = typer.Argument(
            None, help="Path to the repository to visualize."
        ),
        port: int = typer.Option(
            8000, "--port", "-p", help="Port to run the visualizer server on."
        ),
    ) -> None:
        """Run the ``pcg visualize`` shortcut."""
        main_module._load_credentials()
        main_module.visualize_helper(repo, port)

    @app.command("w", rich_help_panel="Shortcuts")
    def watch_abbrev(
        path: str = typer.Argument(".", help="Path to watch"),
        scope: str = typer.Option("auto", "--scope", help="Watch scope."),
    ) -> None:
        """Run the ``pcg watch`` shortcut."""
        watch(path, scope=scope)
