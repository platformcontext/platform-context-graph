"""Ecosystem command registration for the CLI entrypoint."""

from __future__ import annotations

import json
from typing import Any

import typer
from rich import box
from rich.table import Table


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

        graph_builder, _, _, loop = main_module._initialize_services()
        job_manager = JobManager()
        indexer = EcosystemIndexer(graph_builder, job_manager)
        result = loop.run_until_complete(
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

    @ecosystem_app.command("status")
    def ecosystem_status() -> None:
        """Show per-repository indexing status."""
        from platform_context_graph.core.ecosystem_indexer import EcosystemIndexer
        from platform_context_graph.core.jobs import JobManager

        graph_builder, _, _, _ = main_module._initialize_services()
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
                info.get("last_indexed", "")[:19] if info.get("last_indexed") else "",
            )

        main_module.console.print(table)

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

        graph_builder, _, _, loop = main_module._initialize_services()
        indexer = EcosystemIndexer(graph_builder, JobManager())
        result = loop.run_until_complete(
            indexer.update_ecosystem(
                manifest_path=manifest,
                base_path=resolved_base_path,
                parallel=parallel,
            )
        )

        main_module.console.print(f"Updated: {len(result.get('updated', []))}")
        main_module.console.print(f"Skipped: {len(result.get('skipped', []))}")

    @ecosystem_app.command("link")
    def ecosystem_link() -> None:
        """Build cross-repository relationships after indexing."""
        from platform_context_graph.tools.cross_repo_linker import CrossRepoLinker

        graph_builder, _, _, _ = main_module._initialize_services()
        linker = CrossRepoLinker(graph_builder.db_manager)
        stats = linker.link_all()

        table = Table(title="Cross-Repo Relationships Created", box=box.ROUNDED)
        table.add_column("Relationship", style="cyan")
        table.add_column("Count", style="green")
        for relationship_type, count in sorted(stats.items()):
            table.add_row(relationship_type, str(count))
        main_module.console.print(table)

    @ecosystem_app.command("overview")
    def ecosystem_overview() -> None:
        """Show ecosystem overview statistics."""
        graph_builder, _, _, _ = main_module._initialize_services()
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
        graph_builder, _, _, _ = main_module._initialize_services()
        from platform_context_graph.mcp.tools.handlers import ecosystem

        if query_type == "trace":
            result = ecosystem.trace_deployment_chain(graph_builder.db_manager, target)
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
            main_module.console.print(f"[red]Unknown query type: {query_type}[/red]")
            raise typer.Exit(1)

        main_module.console.print_json(json.dumps(result, indent=2, default=str))
