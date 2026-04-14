"""Workspace-oriented CLI helper implementations.

Workspace sync and plan operations previously depended on
``platform_context_graph.runtime.ingester``, which is now deleted.
The Go ingester (``go/cmd/ingester``) owns the deployed write-plane.
Workspace index and watch commands delegate to the Go bootstrap-index.
"""

from __future__ import annotations

import os
from pathlib import Path

from ...indexing.run_status import describe_index_run
from .indexing import index_helper
from .watch import watch_helper


def _api():
    """Return the canonical ``cli_helpers`` module for shared state."""
    from .. import cli_helpers as api

    return api


def _managed_checkout_count(repos_dir: Path) -> int:
    """Return the number of managed git checkouts in the workspace."""

    if not repos_dir.exists():
        return 0
    return sum(
        1 for path in repos_dir.iterdir() if path.is_dir() and (path / ".git").exists()
    )


def workspace_plan_helper() -> None:
    """Preview the repositories selected by the current workspace config."""

    api = _api()
    api.console.print(
        "[bold yellow]Workspace plan is now handled by the Go ingester.[/bold yellow]\n"
        "Use the Go ingester's discovery mode or check docker compose logs."
    )


def workspace_sync_helper() -> None:
    """Clone, update, or copy the configured workspace without indexing."""

    api = _api()
    api.console.print(
        "[bold yellow]Workspace sync is now handled by the Go ingester.[/bold yellow]\n"
        "The Go ingester (pcg-ingester) owns repository discovery and sync.\n"
        "Use 'docker compose up ingester' or the Helm-deployed ingester."
    )


def workspace_index_helper() -> None:
    """Index the configured materialized workspace using the shared index helper."""

    api = _api()
    repos_dir = os.environ.get("PCG_REPOS_DIR", "")
    if not repos_dir:
        api.console.print(
            "[bold red]PCG_REPOS_DIR is not set.[/bold red] "
            "Set it to the workspace directory to index."
        )
        return

    api.console.print("[bold cyan]Workspace Index[/bold cyan]")
    api.console.print(f"[cyan]Workspace:[/cyan] {repos_dir}")
    index_helper(repos_dir)


def workspace_status_helper() -> None:
    """Print the configured workspace status and the latest index summary."""

    api = _api()
    repos_dir = os.environ.get("PCG_REPOS_DIR", "")
    if not repos_dir:
        api.console.print(
            "[bold red]PCG_REPOS_DIR is not set.[/bold red] "
            "Set it to the workspace directory to check status."
        )
        return

    source_mode = os.environ.get("PCG_SOURCE_MODE", "filesystem")
    repos_path = Path(repos_dir)

    api.console.print("[bold cyan]Workspace Status[/bold cyan]")
    api.console.print(f"[cyan]Source mode:[/cyan] {source_mode}")
    api.console.print(f"[cyan]Workspace:[/cyan] {repos_dir}")
    api.console.print(
        f"[cyan]Local checkouts:[/cyan] {_managed_checkout_count(repos_path)}"
    )

    summary = describe_index_run(repos_path)
    if summary is None:
        api.console.print("[yellow]No checkpointed workspace index run found.[/yellow]")
        return

    api.console.print(
        f"[cyan]Latest index run:[/cyan] {summary['run_id']} "
        f"[dim]({summary['status']}, finalization={summary['finalization_status']})[/dim]"
    )
    api.console.print(
        f"[cyan]Repositories:[/cyan] total={summary['repository_count']} "
        f"completed={summary['completed_repositories']} "
        f"failed={summary['failed_repositories']} "
        f"pending={summary['pending_repositories']}"
    )


def workspace_watch_helper(
    *,
    include_repositories: list[str] | None = None,
    exclude_repositories: list[str] | None = None,
    rediscover_interval_seconds: int | None = None,
) -> None:
    """Watch the configured workspace using repo-partitioned watch mode."""

    api = _api()
    repos_dir = os.environ.get("PCG_REPOS_DIR", "")
    if not repos_dir:
        api.console.print(
            "[bold red]PCG_REPOS_DIR is not set.[/bold red] "
            "Set it to the workspace directory to watch."
        )
        return

    api.console.print("[bold cyan]Workspace Watch[/bold cyan]")
    api.console.print(f"[cyan]Workspace:[/cyan] {repos_dir}")
    watch_helper(
        repos_dir,
        scope="workspace",
        include_repositories=include_repositories,
        exclude_repositories=exclude_repositories,
        rediscover_interval_seconds=rediscover_interval_seconds,
    )
