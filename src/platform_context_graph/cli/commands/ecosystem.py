"""Ecosystem command registration for the CLI entrypoint."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich import box
from rich.table import Table

from platform_context_graph.relationships import (
    REPOSITORY_DEPENDENCY_SCOPE,
    RelationshipAssertion,
    get_relationship_store,
)


def _initialize_ecosystem_services(main_module: Any) -> tuple[Any, Any, Any] | None:
    """Return the shared ecosystem service tuple or ``None`` when startup fails."""

    services = main_module._initialize_services()
    if not services or len(services) != 3:
        return None
    if not all(services):
        return None
    return services


def _resolve_target_repositories(
    *,
    code_finder: Any,
    explicit_repo_paths: list[str] | None,
) -> list[Path]:
    """Resolve repository paths for a relationship resolution run."""

    if explicit_repo_paths:
        return [Path(repo_path).resolve() for repo_path in explicit_repo_paths]
    return [
        Path(repo["path"]).resolve()
        for repo in code_finder.list_indexed_repositories()
        if repo.get("path")
    ]


def _require_relationship_store() -> Any:
    """Return the configured relationship store or raise a CLI error."""

    store = get_relationship_store()
    if store is None or not store.enabled:
        typer.echo(
            "Relationship store is not configured. Set "
            "PCG_RELATIONSHIP_STORE_DSN, PCG_CONTENT_STORE_DSN, or "
            "PCG_POSTGRES_DSN.",
            err=True,
        )
        raise typer.Exit(1)
    return store


def register_ecosystem_commands(main_module: Any, app: typer.Typer) -> None:
    """Register ecosystem commands on the root CLI app.

    Args:
        main_module: The imported ``platform_context_graph.cli.main`` module.
        app: The root Typer application.
    """
    ecosystem_app = typer.Typer(
        name="ecosystem",
        help="Ecosystem-level indexing and querying across multiple repos.",
    )
    app.add_typer(ecosystem_app, name="ecosystem")

    @ecosystem_app.command("index")
    def ecosystem_index(
        manifest: str = typer.Argument(
            ..., help="Path to dependency-graph.yaml manifest."
        ),
        base_path: str = typer.Option(
            "", "--base-path", "-b", help="Base directory where repos are cloned."
        ),
        force: bool = typer.Option(
            False, "--force", "-f", help="Force re-index all repos."
        ),
        parallel: int = typer.Option(
            4, "--parallel", "-p", help="Max concurrent repo indexing."
        ),
        clone_missing: bool = typer.Option(
            False, "--clone-missing", help="Clone missing repos via gh CLI."
        ),
    ) -> None:
        """Index all repositories in an ecosystem manifest."""
        resolved_base_path = (
            base_path
            or main_module.config_manager.get_config_value("ECOSYSTEM_BASE_PATH")
            or ""
        )
        if not resolved_base_path:
            main_module.console.print(
                "[red]Error: --base-path required (or set ECOSYSTEM_BASE_PATH in config)[/red]"
            )
            raise typer.Exit(1)

        from platform_context_graph.core.ecosystem_indexer import EcosystemIndexer
        from platform_context_graph.core.jobs import JobManager

        services = _initialize_ecosystem_services(main_module)
        if services is None:
            raise typer.Exit(1)
        db_manager, graph_builder, _ = services
        try:
            job_manager = JobManager()
            indexer = EcosystemIndexer(graph_builder, job_manager)
            result = graph_builder.loop.run_until_complete(
                indexer.index_ecosystem(
                    manifest_path=manifest,
                    base_path=resolved_base_path,
                    force=force,
                    parallel=parallel,
                    clone_missing=clone_missing,
                )
            )
            main_module.console.print(
                f"\n[bold green]Ecosystem: {result.get('ecosystem', 'unknown')}[/bold green]"
            )
            main_module.console.print(f"Total repos: {result.get('total_repos', 0)}")
            main_module.console.print(f"Indexed: {len(result.get('indexed', []))}")
            main_module.console.print(f"Skipped: {len(result.get('skipped', []))}")
            main_module.console.print(f"Failed: {len(result.get('failed', []))}")

            if result.get("missing_repos"):
                main_module.console.print(
                    f"\n[yellow]Missing repos: {', '.join(result['missing_repos'])}[/yellow]"
                )
            if result.get("failed"):
                for failure in result["failed"]:
                    main_module.console.print(
                        f"[red]  Failed: {failure['name']}: {failure['error']}[/red]"
                    )
        finally:
            db_manager.close_driver()

    @ecosystem_app.command("status")
    def ecosystem_status() -> None:
        """Show per-repository indexing status."""
        from platform_context_graph.core.ecosystem_indexer import EcosystemIndexer
        from platform_context_graph.core.jobs import JobManager

        services = _initialize_ecosystem_services(main_module)
        if services is None:
            raise typer.Exit(1)
        db_manager, graph_builder, _ = services
        try:
            indexer = EcosystemIndexer(graph_builder, JobManager())
            status = indexer.get_status()
            if not status.get("repos"):
                main_module.console.print(
                    "[yellow]No ecosystem repos indexed yet.[/yellow]"
                )
                return

            table = Table(title="Ecosystem Indexing Status", box=box.ROUNDED)
            table.add_column("Repository", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Commit", style="dim")
            table.add_column("Files")
            table.add_column("Last Indexed", style="dim")

            for name, info in sorted(status["repos"].items()):
                status_style = {
                    "indexed": "green",
                    "failed": "red",
                    "pending": "yellow",
                }.get(info["status"], "white")
                table.add_row(
                    name,
                    f"[{status_style}]{info['status']}[/{status_style}]",
                    info.get("last_commit", ""),
                    str(info.get("files", "")),
                    (
                        info.get("last_indexed", "")[:19]
                        if info.get("last_indexed")
                        else ""
                    ),
                )

            main_module.console.print(table)
        finally:
            db_manager.close_driver()

    @ecosystem_app.command("update")
    def ecosystem_update(
        manifest: str = typer.Argument(
            ..., help="Path to dependency-graph.yaml manifest."
        ),
        base_path: str = typer.Option(
            "", "--base-path", "-b", help="Base directory where repos are cloned."
        ),
        parallel: int = typer.Option(
            4, "--parallel", "-p", help="Max concurrent repo indexing."
        ),
    ) -> None:
        """Incrementally update only stale repositories."""
        resolved_base_path = (
            base_path
            or main_module.config_manager.get_config_value("ECOSYSTEM_BASE_PATH")
            or ""
        )
        if not resolved_base_path:
            main_module.console.print("[red]Error: --base-path required[/red]")
            raise typer.Exit(1)

        from platform_context_graph.core.ecosystem_indexer import EcosystemIndexer
        from platform_context_graph.core.jobs import JobManager

        services = _initialize_ecosystem_services(main_module)
        if services is None:
            raise typer.Exit(1)
        db_manager, graph_builder, _ = services
        try:
            indexer = EcosystemIndexer(graph_builder, JobManager())
            result = graph_builder.loop.run_until_complete(
                indexer.update_ecosystem(
                    manifest_path=manifest,
                    base_path=resolved_base_path,
                    parallel=parallel,
                )
            )
            main_module.console.print(f"Updated: {len(result.get('updated', []))}")
            main_module.console.print(f"Skipped: {len(result.get('skipped', []))}")
        finally:
            db_manager.close_driver()

    @ecosystem_app.command("link")
    def ecosystem_link() -> None:
        """Build cross-repository relationships after indexing."""
        from platform_context_graph.tools.cross_repo_linker import CrossRepoLinker

        services = _initialize_ecosystem_services(main_module)
        if services is None:
            raise typer.Exit(1)
        db_manager, graph_builder, _ = services
        try:
            linker = CrossRepoLinker(graph_builder.db_manager)
            stats = linker.link_all()

            table = Table(title="Cross-Repo Relationships Created", box=box.ROUNDED)
            table.add_column("Relationship", style="cyan")
            table.add_column("Count", style="green")
            for relationship_type, count in sorted(stats.items()):
                table.add_row(relationship_type, str(count))
            main_module.console.print(table)
        finally:
            db_manager.close_driver()

    @ecosystem_app.command("resolve")
    def ecosystem_resolve(
        repo: list[str] | None = typer.Option(
            None,
            "--repo",
            "-r",
            help="Resolve only the provided already-indexed repository paths.",
        ),
    ) -> None:
        """Resolve evidence-backed repository dependencies for indexed repositories."""

        services = _initialize_ecosystem_services(main_module)
        if services is None:
            raise typer.Exit(1)
        db_manager, graph_builder, code_finder = services
        try:
            committed_repo_paths = _resolve_target_repositories(
                code_finder=code_finder,
                explicit_repo_paths=repo,
            )
            if not committed_repo_paths:
                typer.echo(
                    "No indexed repositories available for relationship resolution."
                )
                raise typer.Exit(1)
            stats = graph_builder._resolve_repository_relationships(
                committed_repo_paths,
                run_id=None,
            )
            typer.echo(json.dumps(stats, sort_keys=True))
        finally:
            db_manager.close_driver()

    @ecosystem_app.command("generation")
    def ecosystem_generation() -> None:
        """Show the active relationship resolution generation."""

        store = _require_relationship_store()
        generation = store.get_active_generation(scope=REPOSITORY_DEPENDENCY_SCOPE)
        if generation is None:
            typer.echo("No active relationship generation.")
            return
        typer.echo(
            json.dumps(
                {
                    "generation_id": generation.generation_id,
                    "scope": generation.scope,
                    "run_id": generation.run_id,
                    "status": generation.status,
                },
                sort_keys=True,
            )
        )

    @ecosystem_app.command("relationships")
    def ecosystem_relationships() -> None:
        """List resolved repository relationships from the active generation."""

        store = _require_relationship_store()
        generation = store.get_active_generation(scope=REPOSITORY_DEPENDENCY_SCOPE)
        relationships = store.list_resolved_relationships(
            scope=REPOSITORY_DEPENDENCY_SCOPE
        )
        if generation is None:
            typer.echo("No active relationship generation.")
            return
        typer.echo(
            f"Active generation: {generation.generation_id} "
            f"(scope={generation.scope}, run_id={generation.run_id or 'adhoc'})"
        )
        if not relationships:
            typer.echo("No resolved relationships.")
            return
        for relationship in relationships:
            typer.echo(
                "\t".join(
                    [
                        relationship.source_repo_id,
                        relationship.relationship_type,
                        relationship.target_repo_id,
                        f"{relationship.confidence:.2f}",
                        str(relationship.evidence_count),
                        relationship.resolution_source,
                    ]
                )
            )

    @ecosystem_app.command("candidates")
    def ecosystem_candidates() -> None:
        """List active relationship candidates before assertion/rejection review."""

        store = _require_relationship_store()
        candidates = store.list_relationship_candidates(
            scope=REPOSITORY_DEPENDENCY_SCOPE,
            relationship_type="DEPENDS_ON",
        )
        if not candidates:
            typer.echo("No active relationship candidates.")
            return
        for candidate in candidates:
            typer.echo(
                "\t".join(
                    [
                        candidate.source_repo_id,
                        candidate.relationship_type,
                        candidate.target_repo_id,
                        f"{candidate.confidence:.2f}",
                        str(candidate.evidence_count),
                    ]
                )
            )

    @ecosystem_app.command("assert-relationship")
    def ecosystem_assert_relationship(
        source_repo_id: str = typer.Argument(
            ..., help="Canonical source repository ID."
        ),
        target_repo_id: str = typer.Argument(
            ..., help="Canonical target repository ID."
        ),
        reason: str = typer.Option(
            ..., "--reason", help="Why the relationship is valid."
        ),
        actor: str = typer.Option(
            "cli", "--actor", help="Actor recording the assertion."
        ),
    ) -> None:
        """Persist an explicit repository dependency assertion."""

        store = _require_relationship_store()
        store.upsert_relationship_assertion(
            RelationshipAssertion(
                source_repo_id=source_repo_id,
                target_repo_id=target_repo_id,
                relationship_type="DEPENDS_ON",
                decision="assert",
                reason=reason,
                actor=actor,
            )
        )
        typer.echo(
            f"Stored assert relationship for {source_repo_id} -> {target_repo_id}"
        )

    @ecosystem_app.command("reject-relationship")
    def ecosystem_reject_relationship(
        source_repo_id: str = typer.Argument(
            ..., help="Canonical source repository ID."
        ),
        target_repo_id: str = typer.Argument(
            ..., help="Canonical target repository ID."
        ),
        reason: str = typer.Option(
            ..., "--reason", help="Why the relationship should be blocked."
        ),
        actor: str = typer.Option(
            "cli", "--actor", help="Actor recording the rejection."
        ),
    ) -> None:
        """Persist an explicit repository dependency rejection."""

        store = _require_relationship_store()
        store.upsert_relationship_assertion(
            RelationshipAssertion(
                source_repo_id=source_repo_id,
                target_repo_id=target_repo_id,
                relationship_type="DEPENDS_ON",
                decision="reject",
                reason=reason,
                actor=actor,
            )
        )
        typer.echo(
            f"Stored reject relationship for {source_repo_id} -> {target_repo_id}"
        )

    @ecosystem_app.command("overview")
    def ecosystem_overview() -> None:
        """Show ecosystem overview statistics."""
        services = _initialize_ecosystem_services(main_module)
        if services is None:
            raise typer.Exit(1)
        db_manager, graph_builder, _ = services
        try:
            from platform_context_graph.mcp.tools.handlers import ecosystem

            result = ecosystem.get_ecosystem_overview(graph_builder.db_manager)
            eco = result.get("ecosystem", {})
            main_module.console.print(
                f"\n[bold cyan]Ecosystem: {eco.get('name', 'N/A')}[/bold cyan]"
            )
            main_module.console.print(f"Organization: {eco.get('org', 'N/A')}\n")

            if result.get("tiers"):
                table = Table(title="Tiers", box=box.ROUNDED)
                table.add_column("Tier", style="cyan")
                table.add_column("Risk", style="yellow")
                table.add_column("Repos")
                for tier in result["tiers"]:
                    table.add_row(
                        tier["tier"],
                        tier.get("risk", ""),
                        ", ".join(tier.get("repos", [])),
                    )
                main_module.console.print(table)

            infra = result.get("infrastructure_counts", {})
            if infra:
                main_module.console.print("\n[bold]Infrastructure Counts:[/bold]")
                for key, value in infra.items():
                    main_module.console.print(f"  {key}: {value}")
        finally:
            db_manager.close_driver()

    @ecosystem_app.command("query")
    def ecosystem_query(
        query_type: str = typer.Argument(
            ..., help="Query type: trace, blast-radius, search, relationships"
        ),
        target: str = typer.Argument("", help="Target name for the query."),
        category: str = typer.Option(
            "", "--category", "-c", help="Resource category filter."
        ),
        target_type: str = typer.Option(
            "repository", "--type", "-t", help="Target type for blast-radius."
        ),
        rel_query: str = typer.Option(
            "", "--rel", "-r", help="Relationship query type."
        ),
    ) -> None:
        """Run ecosystem-level queries."""
        services = _initialize_ecosystem_services(main_module)
        if services is None:
            raise typer.Exit(1)
        db_manager, graph_builder, _ = services
        try:
            from platform_context_graph.mcp.tools.handlers import ecosystem

            if query_type == "trace":
                result = ecosystem.trace_deployment_chain(
                    graph_builder.db_manager, target
                )
            elif query_type in ("blast-radius", "blast_radius"):
                result = ecosystem.find_blast_radius(
                    graph_builder.db_manager, target, target_type
                )
            elif query_type == "search":
                result = ecosystem.find_infra_resources(
                    graph_builder.db_manager, target, category
                )
            elif query_type == "relationships":
                if not rel_query:
                    main_module.console.print(
                        "[red]--rel required for relationships query[/red]"
                    )
                    raise typer.Exit(1)
                result = ecosystem.analyze_infra_relationships(
                    graph_builder.db_manager, rel_query, target
                )
            elif query_type == "summary":
                result = ecosystem.get_repo_summary(graph_builder.db_manager, target)
            else:
                main_module.console.print(
                    f"[red]Unknown query type: {query_type}[/red]"
                )
                raise typer.Exit(1)

            main_module.console.print_json(json.dumps(result, indent=2, default=str))
        finally:
            db_manager.close_driver()
