"""Core non-grouped command registration for the CLI entrypoint."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import typer

from .basic_support import delete_all_repositories, run_doctor
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
        run_doctor(main_module)

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

        delete_all_repositories(main_module)

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
