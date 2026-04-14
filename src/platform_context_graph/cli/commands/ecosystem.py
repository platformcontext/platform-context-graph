"""Ecosystem command registration for the CLI entrypoint."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

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
        raise typer.Exit(
            "Ecosystem indexing has migrated to the Go ingester service."
        )

    @ecosystem_app.command("status")
    def ecosystem_status() -> None:
        """Show per-repository indexing status."""
        raise typer.Exit(
            "Ecosystem indexing has migrated to the Go ingester service."
        )

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
        raise typer.Exit(
            "Ecosystem indexing has migrated to the Go ingester service."
        )

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
        raise typer.Exit(
            "Ecosystem indexing has migrated to the Go ingester service."
        )

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
