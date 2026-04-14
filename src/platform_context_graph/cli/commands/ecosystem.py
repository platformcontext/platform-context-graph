"""Ecosystem command registration for the CLI entrypoint."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import typer
from rich import box
from rich.table import Table

from platform_context_graph.observability import new_request_id
from platform_context_graph.cli.helpers.go_index_runtime import run_go_bootstrap_index

from .ecosystem_relationships import register_ecosystem_relationship_commands


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
    register_ecosystem_relationship_commands(main_module, ecosystem_app)

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
            indexer = EcosystemIndexer(
                graph_builder,
                job_manager,
                index_repository=run_go_bootstrap_index,
            )
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
            indexer = EcosystemIndexer(
                graph_builder,
                JobManager(),
                index_repository=run_go_bootstrap_index,
            )
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
            indexer = EcosystemIndexer(
                graph_builder,
                JobManager(),
                index_repository=run_go_bootstrap_index,
            )
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
        from platform_context_graph.relationships.cross_repo_linker import (
            CrossRepoLinker,
        )

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
            run_id = f"adhoc_{new_request_id()}"
            stats = graph_builder._resolve_repository_relationships(
                committed_repo_paths,
                run_id=run_id,
            )
            typer.echo(json.dumps(stats, sort_keys=True))
        finally:
            db_manager.close_driver()

    @ecosystem_app.command("overview")
    def ecosystem_overview() -> None:
        """Show ecosystem overview statistics."""
        api_url = os.getenv("PCG_API_URL", "http://localhost:8080")
        url = f"{api_url}/api/v0/ecosystem/overview"

        try:
            req = Request(url)
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))

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
        except (URLError, HTTPError) as e:
            main_module.console.print(f"[red]Error calling Go API: {e}[/red]")
            raise typer.Exit(1)

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
        api_url = os.getenv("PCG_API_URL", "http://localhost:8080")

        try:
            if query_type == "trace":
                url = f"{api_url}/api/v0/impact/trace-resource-to-code"
                body = json.dumps({"target": target}).encode("utf-8")
                req = Request(url, data=body, method="POST")
                req.add_header("Content-Type", "application/json")

            elif query_type in ("blast-radius", "blast_radius"):
                url = f"{api_url}/api/v0/impact/blast-radius"
                body = json.dumps({"target": target, "target_type": target_type}).encode("utf-8")
                req = Request(url, data=body, method="POST")
                req.add_header("Content-Type", "application/json")

            elif query_type == "search":
                url = f"{api_url}/api/v0/infra/resources/search"
                body = json.dumps({"query": target, "category": category}).encode("utf-8")
                req = Request(url, data=body, method="POST")
                req.add_header("Content-Type", "application/json")

            elif query_type == "relationships":
                if not rel_query:
                    main_module.console.print(
                        "[red]--rel required for relationships query[/red]"
                    )
                    raise typer.Exit(1)
                url = f"{api_url}/api/v0/infra/relationships"
                body = json.dumps({"entity_id": target, "relationship_type": rel_query}).encode("utf-8")
                req = Request(url, data=body, method="POST")
                req.add_header("Content-Type", "application/json")

            elif query_type == "summary":
                url = f"{api_url}/api/v0/repositories/{target}/context"
                req = Request(url)
                req.add_header("Content-Type", "application/json")

            else:
                main_module.console.print(
                    f"[red]Unknown query type: {query_type}[/red]"
                )
                raise typer.Exit(1)

            with urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))

            main_module.console.print_json(json.dumps(result, indent=2, default=str))

        except (URLError, HTTPError) as e:
            main_module.console.print(f"[red]Error calling Go API: {e}[/red]")
            raise typer.Exit(1)
