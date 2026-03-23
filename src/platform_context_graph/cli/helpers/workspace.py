"""Workspace-oriented CLI helper implementations."""

from __future__ import annotations

from pathlib import Path

from ...indexing.coordinator import describe_index_run
from ...runtime.ingester import RepoSyncConfig, build_workspace_plan, run_workspace_sync
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
    """Print the current workspace discovery plan without mutating the workspace."""

    api = _api()
    try:
        config = RepoSyncConfig.from_env(component="workspace-plan")
        plan = build_workspace_plan(config)
    except Exception as exc:
        api.console.print(f"[bold red]Workspace plan failed:[/bold red] {exc}")
        return

    api.console.print("[bold cyan]Workspace Plan[/bold cyan]")
    api.console.print(f"[cyan]Source mode:[/cyan] {plan['source_mode']}")
    api.console.print(f"[cyan]Workspace:[/cyan] {plan['repos_dir']}")
    api.console.print(
        f"[cyan]Matched repositories:[/cyan] {plan['matched_repositories']}"
    )
    api.console.print(f"[cyan]Already cloned:[/cyan] {plan['already_cloned']}")
    api.console.print(f"[cyan]Stale checkouts:[/cyan] {plan['stale_checkouts']}")
    if plan["repository_ids"]:
        api.console.print("[cyan]Repositories:[/cyan]")
        for repository_id in plan["repository_ids"]:
            api.console.print(f"  - {repository_id}")


def workspace_sync_helper() -> None:
    """Materialize or refresh the configured workspace without indexing."""

    api = _api()
    try:
        config = RepoSyncConfig.from_env(component="workspace-sync")
        result = run_workspace_sync(config)
    except Exception as exc:
        api.console.print(f"[bold red]Workspace sync failed:[/bold red] {exc}")
        raise

    api.console.print("[bold cyan]Workspace Sync[/bold cyan]")
    api.console.print(
        "[cyan]Result:[/cyan] "
        f"discovered={result.discovered} "
        f"cloned={result.cloned} "
        f"updated={result.updated} "
        f"skipped={result.skipped} "
        f"failed={result.failed} "
        f"stale={result.stale}"
    )


def workspace_index_helper() -> None:
    """Index the configured materialized workspace using the shared index helper."""

    api = _api()
    try:
        config = RepoSyncConfig.from_env(component="workspace-index")
    except Exception as exc:
        api.console.print(f"[bold red]Workspace index failed:[/bold red] {exc}")
        return

    api.console.print("[bold cyan]Workspace Index[/bold cyan]")
    api.console.print(f"[cyan]Workspace:[/cyan] {config.repos_dir}")
    index_helper(str(config.repos_dir))


def workspace_status_helper() -> None:
    """Print the configured workspace status and the latest index summary."""

    api = _api()
    try:
        config = RepoSyncConfig.from_env(component="workspace-status")
    except Exception as exc:
        api.console.print(f"[bold red]Workspace status failed:[/bold red] {exc}")
        return

    api.console.print("[bold cyan]Workspace Status[/bold cyan]")
    api.console.print(f"[cyan]Source mode:[/cyan] {config.source_mode}")
    api.console.print(f"[cyan]Workspace:[/cyan] {config.repos_dir}")
    api.console.print(
        f"[cyan]Local checkouts:[/cyan] {_managed_checkout_count(config.repos_dir)}"
    )

    summary = describe_index_run(config.repos_dir)
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
    try:
        config = RepoSyncConfig.from_env(component="workspace-watch")
    except Exception as exc:
        api.console.print(f"[bold red]Workspace watch failed:[/bold red] {exc}")
        return

    api.console.print("[bold cyan]Workspace Watch[/bold cyan]")
    api.console.print(f"[cyan]Workspace:[/cyan] {config.repos_dir}")
    watch_helper(
        str(config.repos_dir),
        scope="workspace",
        include_repositories=include_repositories,
        exclude_repositories=exclude_repositories,
        rediscover_interval_seconds=rediscover_interval_seconds,
    )
