"""Indexing-oriented CLI helper implementations."""

from __future__ import annotations

import time
from pathlib import Path

from ...indexing.coordinator import describe_index_run
from ...core import get_database_manager
from ...tools.code_finder import CodeFinder
from ...platform.package_resolver import get_local_package_path
from .go_index_runtime import run_go_bootstrap_index


def _api():
    """Return the canonical ``cli_helpers`` module for shared state."""
    from .. import cli_helpers as api

    return api


def _initialize_index_status_services():
    """Return optional database services used for local skip/status checks."""

    try:
        db_manager = get_database_manager()
        db_manager.get_driver()
    except Exception:
        return None, None
    return db_manager, CodeFinder(db_manager)


def index_helper(
    path: str,
    *,
    force: bool = False,
    selected_repositories: list[Path] | tuple[Path, ...] | None = None,
    family: str = "index",
    source: str | None = None,
    component: str = "cli",
) -> None:
    """Index a repository path synchronously."""
    return _index_helper(
        path,
        force=force,
        selected_repositories=selected_repositories,
        family=family,
        source=source,
        component=component,
    )


def _index_helper(
    path: str,
    *,
    force: bool,
    selected_repositories: list[Path] | tuple[Path, ...] | None,
    family: str,
    source: str | None,
    component: str,
) -> None:
    """Index a repository path synchronously.

    Args:
        path: Filesystem path to the repository root.
        force: Whether to invalidate an existing checkpoint for the same run.
        selected_repositories: Optional repository subset for coordinated runs.
        family: Run family label used in checkpointing and telemetry.
        source: Source label used in checkpointing and telemetry.
        component: Observability component label for the indexing run.
    """
    api = _api()
    time_start = time.time()
    path_obj = Path(path).resolve()

    if not path_obj.exists():
        api.console.print(f"[red]Error: Path does not exist: {path_obj}[/red]")
        return

    db_manager, code_finder = _initialize_index_status_services()
    try:
        repo_exists = False
        if code_finder is not None:
            indexed_repos = code_finder.list_indexed_repositories()
            repo_exists = any(
                Path(repo["path"]).resolve() == path_obj for repo in indexed_repos
            )

        if repo_exists and not force:
            try:
                with db_manager.get_driver().session() as session:
                    result = session.run(
                        "MATCH (r:Repository {path: $path})-[:REPO_CONTAINS]->(f:File) "
                        "RETURN count(DISTINCT f) as file_count",
                        path=str(path_obj),
                    )
                    record = result.single()
                    file_count = record["file_count"] if record else 0

                    if file_count > 0:
                        api.console.print(
                            f"[yellow]Repository '{path}' is already indexed with "
                            f"{file_count} files. Skipping.[/yellow]"
                        )
                        api.console.print(
                            "[dim]💡 Tip: Use 'pcg index --force' to re-index[/dim]"
                        )
                        return

                    api.console.print(
                        f"[yellow]Repository '{path}' exists but has no files "
                        "(likely interrupted). Re-indexing...[/yellow]"
                    )
            except Exception as exc:
                api.console.print(
                    "[yellow]Warning: Could not check file count: "
                    f"{exc}. Proceeding with indexing...[/yellow]"
                )

        api.console.print(f"Starting indexing for: {path_obj}")
        try:
            from platform_context_graph.cli.config_manager import (
                get_index_runtime_config,
            )

            runtime_config = get_index_runtime_config()
            api.console.print(
                "[dim]Indexing config: "
                f"parse workers={runtime_config['parse_workers']}, "
                f"queue depth={runtime_config['queue_depth']}"
                "[/dim]"
            )
        except Exception as exc:
            api.console.print(
                "[yellow]Warning: Could not load indexing runtime config: "
                f"{exc}[/yellow]"
            )

        run_go_bootstrap_index(
            path_obj,
            selected_repositories=(
                [repo_path.resolve() for repo_path in selected_repositories]
                if selected_repositories
                else None
            ),
            force=force,
        )
        elapsed = time.time() - time_start
        api.console.print(
            f"[green]Successfully finished indexing: {path} in {elapsed:.2f} seconds[/green]"
        )
        try:
            from platform_context_graph.cli.config_manager import get_config_value

            auto_watch = get_config_value("ENABLE_AUTO_WATCH")
            if auto_watch and str(auto_watch).lower() == "true":
                api.console.print(
                    "\n[cyan]🔍 ENABLE_AUTO_WATCH is enabled. Starting watcher...[/cyan]"
                )
                api.watch_helper(path)
                return
        except Exception as exc:
            api.console.print(
                    "[yellow]Warning: Could not check ENABLE_AUTO_WATCH: " f"{exc}[/yellow]"
                )
    except Exception as exc:
        api.console.print(
            f"[bold red]An error occurred during indexing:[/bold red] {exc}"
        )
        raise
    finally:
        if db_manager is not None:
            db_manager.close_driver()


def add_package_helper(package_name: str, language: str) -> None:
    """Index a dependency package.

    Args:
        package_name: Package name to resolve locally.
        language: Language ecosystem used to resolve the package.
    """
    api = _api()
    services = api._initialize_services()
    if not all(services):
        return

    db_manager, _graph_builder, code_finder = services
    package_path_str = get_local_package_path(package_name, language)
    if not package_path_str:
        api.console.print(
            "[red]Error: Could not find package "
            f"'{package_name}' for language '{language}'.[/red]"
        )
        db_manager.close_driver()
        return

    package_path = Path(package_path_str)
    indexed_repos = code_finder.list_indexed_repositories()
    if any(
        repo.get("name") == package_name
        for repo in indexed_repos
        if repo.get("is_dependency")
    ):
        api.console.print(
            f"[yellow]Package '{package_name}' is already indexed. Skipping.[/yellow]"
        )
        db_manager.close_driver()
        return

    api.console.print(
        f"Starting indexing for package '{package_name}' at: {package_path}"
    )

    try:
        run_go_bootstrap_index(
            package_path.resolve(),
            force=False,
            is_dependency=True,
            package_name=package_name,
            language=language,
        )
        api.console.print(
            f"[green]Successfully finished indexing package: {package_name}[/green]"
        )
    except Exception as exc:
        api.console.print(
            "[bold red]An error occurred during package indexing:[/bold red] " f"{exc}"
        )
        raise
    finally:
        db_manager.close_driver()


def reindex_helper(path: str) -> None:
    """Force a delete-and-rebuild cycle for a repository.

    Args:
        path: Filesystem path to the repository root.
    """
    _index_helper(
        path,
        force=True,
        selected_repositories=None,
        family="index",
        source=None,
        component="cli",
    )


def update_helper(path: str) -> None:
    """Refresh a repository index using the reindex flow.

    Args:
        path: Filesystem path to the repository root.
    """
    api = _api()
    api.console.print("[cyan]Updating repository index...[/cyan]")
    reindex_helper(path)


def index_status_helper(path_or_run_id: str | None = None) -> None:
    """Display the latest checkpointed index run status for a path or run ID."""

    api = _api()
    target = path_or_run_id or str(Path.cwd())
    summary = describe_index_run(target)
    if summary is None:
        api.console.print(
            f"[yellow]No checkpointed index run found for '{target}'.[/yellow]"
        )
        return

    api.console.print(
        f"[bold cyan]Index Run:[/bold cyan] {summary['run_id']} "
        f"[dim]({summary['status']}, finalization={summary['finalization_status']})[/dim]"
    )
    api.console.print(f"[cyan]Root:[/cyan] {summary['root_path']}")
    api.console.print(
        "[cyan]Repositories:[/cyan] "
        f"{summary['completed_repositories']} completed / "
        f"{summary['failed_repositories']} failed / "
        f"{summary['pending_repositories']} pending "
        f"of {summary['repository_count']}"
    )
    if summary.get("last_error"):
        api.console.print(f"[yellow]Last error:[/yellow] {summary['last_error']}")
