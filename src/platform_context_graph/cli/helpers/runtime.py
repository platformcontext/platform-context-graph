"""Runtime helpers for CLI graph operations.

This module owns the shared service bootstrap and indexing progress loop used by
the CLI helper commands.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from ...core import get_database_manager
from ...core.jobs import JobManager, JobStatus
from ...tools.code_finder import CodeFinder
from ...tools.graph_builder import GraphBuilder

console = Console()


def _initialize_services():
    """Initialize the database, graph builder, and code finder services.

    Returns:
        A tuple containing the database manager, graph builder, and code finder.
        When initialization fails, every tuple element is ``None``.
    """
    console.print("[dim]Initializing services and database connection...[/dim]")
    try:
        db_manager = get_database_manager()
    except ValueError as exc:
        console.print(f"[bold red]Database Configuration Error:[/bold red] {exc}")
        return None, None, None

    try:
        db_manager.get_driver()
    except Exception as exc:
        from ...core.database_falkordb import FalkorDBUnavailableError

        if isinstance(exc, FalkorDBUnavailableError):
            console.print(
                f"[yellow]⚠ FalkorDB Lite is not functional in this environment: {exc}[/yellow]"
            )
            console.print(
                "[cyan]Falling back to KùzuDB for a reliable experience...[/cyan]"
            )
            try:
                db_manager.close_driver()
            except Exception:
                pass

            from ...core.database_kuzu import KuzuDBManager

            db_manager = KuzuDBManager()
            try:
                db_manager.get_driver()
                console.print(
                    "[green]✓[/green] Successfully switched to KùzuDB fallback"
                )
            except Exception as kuzu_exc:
                console.print(
                    "[bold red]Critical Error:[/bold red] "
                    f"Both FalkorDB and KùzuDB failed: {kuzu_exc}"
                )
                return None, None, None
        else:
            console.print(f"[bold red]Database Connection Error:[/bold red] {exc}")
            console.print(
                "Please ensure your database is configured correctly or run 'pcg doctor'."
            )
            return None, None, None

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    graph_builder = GraphBuilder(db_manager, JobManager(), loop)
    code_finder = CodeFinder(db_manager)
    console.print("[dim]Services initialized.[/dim]")
    return db_manager, graph_builder, code_finder


async def _run_index_with_progress(
    graph_builder: GraphBuilder,
    path_obj: Path,
    is_dependency: bool = False,
    *,
    force: bool = False,
    selected_repositories: list[Path] | tuple[Path, ...] | None = None,
    family: str = "index",
    source: str | None = None,
    component: str = "cli",
) -> None:
    """Run graph indexing while rendering a Rich progress bar.

    Args:
        graph_builder: Graph builder used to index the target path.
        path_obj: Repository or package path to index.
        is_dependency: Whether the indexed path should be tracked as a dependency.
        force: Whether to invalidate an existing checkpoint for the same run.
        selected_repositories: Optional repository subset for coordinated runs.
        family: Run family label used in checkpointing and telemetry.
        source: Source label used in checkpointing and telemetry.
        component: Observability component label for the indexing run.

    Raises:
        RuntimeError: If the indexing job finishes in a failed state.
        Exception: Propagates any unexpected indexing exception.
    """
    job_id = graph_builder.job_manager.create_job(
        str(path_obj),
        is_dependency=is_dependency,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        TextColumn("[dim]{task.fields[filename]}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task(
            "Indexing...",
            total=None,
            filename="",
        )
        indexing_task = asyncio.create_task(
            graph_builder.build_graph_from_path_async(
                path_obj,
                is_dependency=is_dependency,
                job_id=job_id,
                force=force,
                selected_repositories=selected_repositories,
                family=family,
                source=source,
                component=component,
            )
        )

        while not indexing_task.done():
            job = graph_builder.job_manager.get_job(job_id)
            if job:
                if job.total_files > 0:
                    progress.update(
                        task_id,
                        total=job.total_files,
                        completed=job.processed_files,
                    )

                current_file = job.current_file or ""
                if len(current_file) > 40:
                    current_file = "..." + current_file[-37:]
                progress.update(task_id, filename=current_file)

                if job.status in {
                    JobStatus.COMPLETED,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                }:
                    break

            await asyncio.sleep(0.1)

        await indexing_task
        job = graph_builder.job_manager.get_job(job_id)
        if job and job.status == JobStatus.FAILED:
            error_msg = job.errors[0] if job.errors else "Unknown error"
            raise RuntimeError(error_msg)
