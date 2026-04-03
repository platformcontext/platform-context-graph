"""Standalone finalization helper for re-running finalization stages."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("pcg.cli.finalize")


def _build_checkouts_from_graph(driver: Any) -> list[Any]:
    """Build RepositoryCheckout records from Neo4j Repository nodes.

    This bypasses the filesystem-dependent build_repository_checkouts() by
    reading repository metadata directly from the graph.  Used when repos
    are not cloned locally (e.g. restored database backup).

    Args:
        driver: Neo4j driver instance.

    Returns:
        List of RepositoryCheckout objects for all repositories in the graph.
    """
    from platform_context_graph.relationships.identity import canonical_checkout_id
    from platform_context_graph.relationships.models import RepositoryCheckout

    with driver.session() as session:
        rows = session.run(
            "MATCH (r:Repository) "
            "RETURN r.id AS id, r.name AS name, "
            "       r.repo_slug AS repo_slug, "
            "       r.remote_url AS remote_url, "
            "       r.path AS path"
        ).data()

    checkouts = []
    for row in rows:
        repo_id = row["id"]
        local_path = row.get("path") or ""
        checkouts.append(
            RepositoryCheckout(
                checkout_id=canonical_checkout_id(
                    logical_repo_id=repo_id,
                    checkout_path=local_path,
                ),
                logical_repo_id=repo_id,
                repo_name=row["name"],
                repo_slug=row.get("repo_slug"),
                remote_url=row.get("remote_url"),
                checkout_path=local_path,
            )
        )
    return checkouts


def _build_repo_paths_from_graph(driver: Any) -> list[Path]:
    """Return Path objects for all indexed repositories from the graph.

    Args:
        driver: Neo4j driver instance.

    Returns:
        List of Path objects for committed repositories.
    """
    with driver.session() as session:
        rows = session.run("MATCH (r:Repository) RETURN r.path AS path").data()
    return [Path(row["path"]) for row in rows if row.get("path")]


def _run_relationship_resolution(
    *,
    driver: Any,
    db_manager: Any,
    run_id: str,
    console: Any,
) -> None:
    """Run relationship resolution using graph-derived checkouts.

    This bypasses the default resolver path which calls
    ``build_repository_checkouts(repo_paths)`` — that function shells out
    to ``git remote`` for every repo path, which is slow (46s for 899 repos)
    and fails entirely when repos aren't cloned locally.

    Instead, we build checkouts from Neo4j Repository nodes and call
    the resolver stages directly.

    Args:
        driver: Neo4j driver instance.
        db_manager: Database manager for Neo4j access.
        run_id: Run identifier for the generation.
        console: Rich console for output.
    """

    from platform_context_graph.relationships.execution import (
        discover_repository_dependency_evidence,
        project_resolved_relationships,
    )
    from platform_context_graph.relationships.state import get_relationship_store
    from platform_context_graph.relationships.resolver import (
        collect_canonical_entities,
        dedupe_relationship_evidence_facts,
        resolve_repository_relationships,
    )

    checkouts = _build_checkouts_from_graph(driver)
    console.print(f"  [dim]Built {len(checkouts)} checkouts from graph[/dim]")

    evidence_facts = discover_repository_dependency_evidence(
        driver,
        checkouts=checkouts,
    )
    evidence_facts = dedupe_relationship_evidence_facts(evidence_facts)
    console.print(f"  [dim]Discovered {len(evidence_facts)} evidence facts[/dim]")

    store = get_relationship_store()
    if store is None or not store.enabled:
        console.print(
            "  [yellow]Relationship store not configured — skipping.[/yellow]"
        )
        return

    assertions = store.list_relationship_assertions()
    candidates, resolved = resolve_repository_relationships(
        evidence_facts,
        assertions,
    )
    console.print(
        f"  [dim]Resolved {len(resolved)} relationships "
        f"from {len(candidates)} candidates[/dim]"
    )

    entities = collect_canonical_entities(
        checkouts=checkouts,
        evidence_facts=evidence_facts,
        candidates=candidates,
        resolved=resolved,
    )

    generation = store.replace_generation(
        scope="repo_dependencies",
        run_id=run_id,
        checkouts=checkouts,
        entities=entities,
        evidence_facts=evidence_facts,
        candidates=candidates,
        resolved=resolved,
    )
    console.print(f"  [dim]Persisted generation {generation.generation_id}[/dim]")

    project_resolved_relationships(
        db_manager=db_manager,
        generation_id=generation.generation_id,
        resolved=resolved,
    )
    console.print(f"  [dim]Projected {len(resolved)} relationships into Neo4j[/dim]")

    store.activate_generation(
        scope="repo_dependencies",
        generation_id=generation.generation_id,
    )


def finalize_helper(
    *,
    stages: list[str] | None = None,
    run_id: str | None = None,
    dry_run: bool = False,
) -> None:
    """Run finalization stages against an existing graph.

    This command re-runs finalization stages without re-indexing.  It is
    designed for two scenarios:

    1. A previous index run whose finalization failed (e.g. Neo4j connection
       drop) — re-run the missing stages to complete the graph.
    2. A restored database backup from ops-qa — run stages 4-5 (workloads +
       relationship_resolution) to create deployment chain edges.

    Args:
        stages: Specific stages to run.  Defaults to graph-only stages
            (workloads, relationship_resolution) when NDJSON snapshots are
            not available, or all 5 stages when snapshots exist.
        run_id: Optional run ID to associate with the finalization.
        dry_run: When True, report what would run without executing.
    """
    from rich.console import Console
    from rich.table import Table

    from ..helpers.runtime import _initialize_services

    console = Console(stderr=True)

    ALL_STAGES = [
        "inheritance",
        "function_calls",
        "infra_links",
        "workloads",
        "relationship_resolution",
    ]
    GRAPH_ONLY_STAGES = ["workloads", "relationship_resolution"]
    FILE_DEPENDENT_STAGES = {"inheritance", "function_calls", "infra_links"}

    console.print("[bold cyan]PCG Standalone Finalization[/bold cyan]")
    console.print()

    # --- Initialize services ---
    services = _initialize_services()
    if not all(services):
        console.print("[red]Failed to initialize services.[/red]")
        return
    db_manager, graph_builder, _code_finder = services

    driver = db_manager.get_driver()

    # --- Determine available stages ---
    repo_paths = _build_repo_paths_from_graph(driver)
    repo_count = len(repo_paths)
    if repo_count == 0:
        console.print(
            "[red]No repositories found in the graph. Nothing to finalize.[/red]"
        )
        db_manager.close_driver()
        return

    console.print(f"[dim]Found {repo_count} repositories in the graph.[/dim]")

    # Check if NDJSON snapshots are available for file-dependent stages
    snapshots_available = False
    existing_state = None
    if run_id:
        from platform_context_graph.indexing.coordinator_storage import (
            _load_run_state_by_id,
            _snapshot_file_data_exists,
        )

        existing_state = _load_run_state_by_id(run_id)
        if existing_state is not None:
            console.print(
                f"[dim]Found existing run state: {run_id} "
                f"(status={existing_state.status}, "
                f"finalization={existing_state.finalization_status})[/dim]"
            )
            # Check if snapshot files exist for any committed repo
            for repo_state in existing_state.repositories.values():
                if repo_state.status == "completed":
                    if _snapshot_file_data_exists(run_id, Path(repo_state.repo_path)):
                        snapshots_available = True
                        break

    # Determine which stages to run
    if stages:
        requested_stages = [s for s in stages if s in ALL_STAGES]
        invalid = [s for s in stages if s not in ALL_STAGES]
        if invalid:
            console.print(
                f"[yellow]Ignoring unknown stages: {', '.join(invalid)}[/yellow]"
            )
    else:
        requested_stages = ALL_STAGES if snapshots_available else GRAPH_ONLY_STAGES

    # Warn about file-dependent stages without snapshots
    file_stages_requested = [s for s in requested_stages if s in FILE_DEPENDENT_STAGES]
    if file_stages_requested and not snapshots_available:
        console.print(
            f"[yellow]Skipping file-dependent stages {file_stages_requested} "
            f"(no NDJSON snapshots available).[/yellow]"
        )
        requested_stages = [
            s for s in requested_stages if s not in FILE_DEPENDENT_STAGES
        ]

    if not requested_stages:
        console.print("[red]No stages to run.[/red]")
        db_manager.close_driver()
        return

    # --- Display plan ---
    table = Table(title="Finalization Plan")
    table.add_column("Stage", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Requires Files", style="dim")
    for stage in ALL_STAGES:
        if stage in requested_stages:
            status = "WILL RUN"
            style = "green"
        elif stage in FILE_DEPENDENT_STAGES and not snapshots_available:
            status = "SKIPPED (no snapshots)"
            style = "yellow"
        else:
            status = "SKIPPED"
            style = "dim"
        table.add_row(
            stage,
            f"[{style}]{status}[/{style}]",
            "Yes" if stage in FILE_DEPENDENT_STAGES else "No",
        )
    console.print(table)
    console.print()

    if dry_run:
        console.print("[yellow]Dry run — no changes made.[/yellow]")
        db_manager.close_driver()
        return

    # --- Execute stages ---
    stage_timings: dict[str, float] = {}
    total_start = time.monotonic()

    for stage_name in requested_stages:
        console.print(f"[cyan]Running stage: {stage_name}...[/cyan]")
        stage_start = time.monotonic()

        try:
            if stage_name == "workloads":
                result = graph_builder._materialize_workloads()
                console.print(f"  [dim]Workloads result: {result}[/dim]")

            elif stage_name == "relationship_resolution":
                _run_relationship_resolution(
                    driver=driver,
                    db_manager=db_manager,
                    run_id=run_id or "finalize-standalone",
                    console=console,
                )

            elif stage_name == "infra_links" and snapshots_available:
                from platform_context_graph.indexing.coordinator_storage import (
                    _iter_snapshot_file_data,
                )

                def _infra_data_iter() -> Any:
                    """Yield file data for all completed repos."""
                    for repo_state in existing_state.repositories.values():
                        if repo_state.status == "completed":
                            yield from _iter_snapshot_file_data(
                                run_id, Path(repo_state.repo_path)
                            )

                graph_builder._create_all_infra_links(_infra_data_iter())

            elif stage_name == "inheritance" and snapshots_available:
                from platform_context_graph.indexing.coordinator_storage import (
                    _iter_snapshot_file_data,
                )

                def _inheritance_data_iter() -> Any:
                    """Yield file data for all completed repos."""
                    for repo_state in existing_state.repositories.values():
                        if repo_state.status == "completed":
                            yield from _iter_snapshot_file_data(
                                run_id, Path(repo_state.repo_path)
                            )

                graph_builder._create_all_inheritance_links(
                    _inheritance_data_iter(), {}
                )

            elif stage_name == "function_calls" and snapshots_available:
                from platform_context_graph.indexing.coordinator_storage import (
                    _iter_snapshot_file_data,
                )

                for repo_state in existing_state.repositories.values():
                    if repo_state.status == "completed":
                        graph_builder._create_all_function_calls(
                            _iter_snapshot_file_data(
                                run_id, Path(repo_state.repo_path)
                            ),
                            {},
                        )

            elapsed = time.monotonic() - stage_start
            stage_timings[stage_name] = elapsed
            console.print(f"  [green]Completed {stage_name} in {elapsed:.1f}s[/green]")

        except Exception as exc:
            elapsed = time.monotonic() - stage_start
            stage_timings[stage_name] = elapsed
            console.print(
                f"  [red]FAILED {stage_name} after {elapsed:.1f}s: {exc}[/red]"
            )
            logger.exception("Finalization stage %s failed", stage_name)
            # Continue to next stage — don't abort the whole run
            continue

    total_elapsed = time.monotonic() - total_start

    # --- Summary ---
    console.print()
    summary_table = Table(title="Finalization Results")
    summary_table.add_column("Stage", style="cyan")
    summary_table.add_column("Duration", style="green")
    for stage_name, duration in stage_timings.items():
        summary_table.add_row(stage_name, f"{duration:.1f}s")
    summary_table.add_row("[bold]Total[/bold]", f"[bold]{total_elapsed:.1f}s[/bold]")
    console.print(summary_table)

    db_manager.close_driver()
    console.print("[bold green]Finalization complete.[/bold green]")
