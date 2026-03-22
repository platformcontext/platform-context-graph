"""Watch-mode CLI helper implementations."""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

from ...core.jobs import JobManager
from ...core.watcher import CodeWatcher


def _api():
    """Return the canonical ``cli_helpers`` module for shared state."""
    from .. import cli_helpers as api

    return api


def _configure_watchdog_logging() -> None:
    """Reduce watchdog log verbosity for CLI watch mode."""
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("watchdog.observers").setLevel(logging.WARNING)
    logging.getLogger("watchdog.observers.inotify_buffer").setLevel(logging.WARNING)


def watch_helper(path: str) -> None:
    """Watch a directory and keep the graph updated.

    Args:
        path: Filesystem path to watch.
    """
    api = _api()
    _configure_watchdog_logging()
    services = api._initialize_services()
    if not all(services):
        return

    db_manager, graph_builder, code_finder = services
    path_obj = Path(path).resolve()

    if not path_obj.exists():
        api.console.print(f"[red]Error: Path does not exist: {path_obj}[/red]")
        db_manager.close_driver()
        return
    if not path_obj.is_dir():
        api.console.print(f"[red]Error: Path must be a directory: {path_obj}[/red]")
        db_manager.close_driver()
        return

    api.console.print(f"[bold cyan]🔍 Watching {path_obj} for changes...[/bold cyan]")
    indexed_repos = code_finder.list_indexed_repositories()
    is_indexed = any(Path(repo["path"]).resolve() == path_obj for repo in indexed_repos)

    watcher = CodeWatcher(graph_builder, JobManager())
    try:
        watcher.start()

        if is_indexed:
            api.console.print(
                "[green]✓[/green] Already indexed (no initial scan needed)"
            )
            watcher.watch_directory(str(path_obj), perform_initial_scan=False)
        else:
            api.console.print(
                "[yellow]⚠[/yellow]  Not indexed yet. Performing initial scan..."
            )

            async def do_index() -> None:
                """Index the repository before watch mode begins."""
                await graph_builder.build_graph_from_path_async(
                    path_obj,
                    is_dependency=False,
                )

            asyncio.run(do_index())
            api.console.print("[green]✓[/green] Initial scan complete")
            watcher.watch_directory(str(path_obj), perform_initial_scan=False)

        api.console.print(
            "[bold green]👀 Monitoring for file changes...[/bold green] "
            "(Press Ctrl+C to stop)"
        )
        api.console.print(
            "[dim]💡 Tip: Open a new terminal window to continue working[/dim]\n"
        )

        stop_event = threading.Event()
        try:
            stop_event.wait()
        except KeyboardInterrupt:
            api.console.print("\n[yellow]🛑 Stopping watcher...[/yellow]")
    except KeyboardInterrupt:
        api.console.print("\n[yellow]🛑 Stopping watcher...[/yellow]")
    except Exception as exc:
        api.console.print(f"[bold red]An error occurred:[/bold red] {exc}")
    finally:
        watcher.stop()
        db_manager.close_driver()
        api.console.print("[green]✓[/green] Watcher stopped. Graph is up to date.")


def unwatch_helper(path: str) -> None:
    """Explain how to stop CLI watch mode.

    Args:
        path: Path provided by the user for context in the output.
    """
    api = _api()
    api.console.print(
        "[yellow]⚠️  Note: 'pcg unwatch' only works when the watcher is running via MCP server.[/yellow]"
    )
    api.console.print(
        "[dim]For CLI watch mode, simply press Ctrl+C in the watch terminal.[/dim]"
    )
    api.console.print(f"\n[cyan]Path specified:[/cyan] {Path(path).resolve()}")


def list_watching_helper() -> None:
    """Explain how to list watched paths for the active watcher."""
    api = _api()
    api.console.print(
        "[yellow]⚠️  Note: 'pcg watching' only works when the watcher is running via MCP server.[/yellow]"
    )
    api.console.print(
        "[dim]For CLI watch mode, check the terminal where you ran 'pcg watch'.[/dim]"
    )
    api.console.print("\n[cyan]To see watched directories in MCP mode:[/cyan]")
    api.console.print("  1. Start the MCP server: pcg mcp start")
    api.console.print("  2. Use the 'list_watched_paths' MCP tool from your IDE")
