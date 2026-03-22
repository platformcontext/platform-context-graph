"""Database and reporting CLI helper implementations."""

from __future__ import annotations

import json
from pathlib import Path

from rich.table import Table

_FORBIDDEN_WRITE_KEYWORDS = (
    "CREATE",
    "MERGE",
    "DELETE",
    "SET",
    "REMOVE",
    "DROP",
    "CALL apoc",
)


def _api():
    """Return the canonical ``cli_helpers`` module for shared state."""
    from .. import cli_helpers as api

    return api


def _ensure_read_only_query(query: str) -> bool:
    """Validate that a Cypher query is read-only.

    Args:
        query: Cypher query supplied by the CLI caller.

    Returns:
        ``True`` when the query is considered read-only, otherwise ``False``.
    """
    api = _api()
    if any(keyword in query.upper() for keyword in _FORBIDDEN_WRITE_KEYWORDS):
        api.console.print(
            "[bold red]Error: This command only supports read-only queries.[/bold red]"
        )
        return False
    return True


def list_repos_helper() -> None:
    """List all indexed repositories in a table."""
    api = _api()
    services = api._initialize_services()
    if not all(services):
        return

    db_manager, _, code_finder = services
    try:
        repos = code_finder.list_indexed_repositories()
        if not repos:
            api.console.print("[yellow]No repositories indexed yet.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Name", style="dim")
        table.add_column("Path")
        table.add_column("Type")

        for repo in repos:
            repo_type = "Dependency" if repo.get("is_dependency") else "Project"
            table.add_row(repo["name"], repo["path"], repo_type)

        api.console.print(table)
    except Exception as exc:
        api.console.print(f"[bold red]An error occurred:[/bold red] {exc}")
    finally:
        db_manager.close_driver()


def delete_helper(repo_path: str) -> None:
    """Delete a repository from the graph database.

    Args:
        repo_path: Repository path used as the deletion key.
    """
    api = _api()
    services = api._initialize_services()
    if not all(services):
        return

    db_manager, graph_builder, _ = services
    try:
        if graph_builder.delete_repository_from_graph(repo_path):
            api.console.print(
                f"[green]Successfully deleted repository: {repo_path}[/green]"
            )
        else:
            api.console.print(
                f"[yellow]Repository not found in graph: {repo_path}[/yellow]"
            )
            api.console.print(
                "[dim]Tip: Use 'pcg list' to see available repositories.[/dim]"
            )
    except Exception as exc:
        api.console.print(f"[bold red]An error occurred:[/bold red] {exc}")
    finally:
        db_manager.close_driver()


def cypher_helper(query: str) -> None:
    """Execute a read-only Cypher query and print JSON records.

    Args:
        query: Cypher query to run.
    """
    api = _api()
    services = api._initialize_services()
    if not all(services):
        return

    db_manager, _, _ = services
    if not _ensure_read_only_query(query):
        db_manager.close_driver()
        return

    try:
        with db_manager.get_driver().session() as session:
            result = session.run(query)
            records = [record.data() for record in result]
            api.console.print(json.dumps(records, indent=2))
    except Exception as exc:
        api.console.print(
            "[bold red]An error occurred while executing query:[/bold red] " f"{exc}"
        )
    finally:
        db_manager.close_driver()


def cypher_helper_visual(query: str) -> None:
    """Execute a read-only Cypher query and visualize the result set.

    Args:
        query: Cypher query to run.
    """
    api = _api()
    from ..visualizer import visualize_cypher_results

    services = api._initialize_services()
    if not all(services):
        return

    db_manager, _, _ = services
    if not _ensure_read_only_query(query):
        db_manager.close_driver()
        return

    try:
        with db_manager.get_driver().session() as session:
            result = session.run(query)
            records = [record.data() for record in result]
            if not records:
                api.console.print("[yellow]No results to visualize.[/yellow]")
                return
            visualize_cypher_results(records, query)
    except Exception as exc:
        api.console.print(
            "[bold red]An error occurred while executing query:[/bold red] " f"{exc}"
        )
    finally:
        db_manager.close_driver()


def clean_helper() -> None:
    """Remove orphaned nodes from the database."""
    api = _api()
    services = api._initialize_services()
    if not all(services):
        return

    db_manager, _, _ = services
    api.console.print("[cyan]🧹 Cleaning database (removing orphaned nodes)...[/cyan]")

    try:
        db_type = db_manager.__class__.__name__
        is_falkordb = "Falkor" in db_type
        total_deleted = 0
        batch_size = 1000

        with db_manager.get_driver().session() as session:
            while True:
                if is_falkordb:
                    query = """
                    MATCH (n)
                    WHERE NOT (n:Repository)
                    OPTIONAL MATCH path = (n)-[*..10]-(r:Repository)
                    WITH n, path
                    WHERE path IS NULL
                    WITH n LIMIT $batch_size
                    DETACH DELETE n
                    RETURN count(n) as deleted
                    """
                else:
                    query = """
                    MATCH (n)
                    WHERE NOT (n:Repository)
                      AND NOT EXISTS {
                        MATCH (n)-[*..10]-(r:Repository)
                      }
                    WITH n LIMIT $batch_size
                    DETACH DELETE n
                    RETURN count(n) as deleted
                    """

                result = session.run(query, batch_size=batch_size)
                record = result.single()
                deleted_count = record["deleted"] if record else 0
                total_deleted += deleted_count

                if deleted_count == 0:
                    break

                api.console.print(
                    f"[dim]Deleted {deleted_count} orphaned nodes (batch)...[/dim]"
                )

            if total_deleted > 0:
                api.console.print(
                    f"[green]✓[/green] Deleted {total_deleted} orphaned nodes total"
                )
            else:
                api.console.print("[green]✓[/green] No orphaned nodes found")

            api.console.print("[dim]Checking for duplicate relationships...[/dim]")

        api.console.print("[green]✅ Database cleanup complete![/green]")
    except Exception as exc:
        api.console.print(
            f"[bold red]An error occurred during cleanup:[/bold red] {exc}"
        )
    finally:
        db_manager.close_driver()


def stats_helper(path: str | None = None) -> None:
    """Show repository or global graph statistics.

    Args:
        path: Optional repository path to scope the statistics query.
    """
    api = _api()
    services = api._initialize_services()
    if not all(services):
        return

    db_manager, _, _ = services

    try:
        if path:
            path_obj = Path(path).resolve()
            api.console.print(f"[cyan]📊 Statistics for: {path_obj}[/cyan]\n")

            with db_manager.get_driver().session() as session:
                repo_query = "MATCH (r:Repository {path: $path}) RETURN r"
                result = session.run(repo_query, path=str(path_obj))
                if not result.single():
                    api.console.print(f"[red]Repository not found: {path_obj}[/red]")
                    return

                file_query = (
                    "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(f:File) "
                    "RETURN count(f) as c"
                )
                func_query = (
                    "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(func:Function) "
                    "RETURN count(func) as c"
                )
                class_query = (
                    "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(c:Class) "
                    "RETURN count(c) as c"
                )
                module_query = (
                    "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(f:File)"
                    "-[:IMPORTS]->(m:Module) RETURN count(DISTINCT m) as c"
                )

                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Metric", style="cyan")
                table.add_column("Count", style="green", justify="right")
                table.add_row(
                    "Files",
                    str(session.run(file_query, path=str(path_obj)).single()["c"]),
                )
                table.add_row(
                    "Functions",
                    str(session.run(func_query, path=str(path_obj)).single()["c"]),
                )
                table.add_row(
                    "Classes",
                    str(session.run(class_query, path=str(path_obj)).single()["c"]),
                )
                table.add_row(
                    "Imported Modules",
                    str(session.run(module_query, path=str(path_obj)).single()["c"]),
                )
                api.console.print(table)
            return

        api.console.print("[cyan]📊 Overall Database Statistics[/cyan]\n")
        with db_manager.get_driver().session() as session:
            repo_count = session.run(
                "MATCH (r:Repository) RETURN count(r) as c"
            ).single()["c"]

            if repo_count <= 0:
                api.console.print("[yellow]No data indexed yet.[/yellow]")
                return

            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Metric", style="cyan")
            table.add_column("Count", style="green", justify="right")
            table.add_row("Repositories", str(repo_count))
            table.add_row(
                "Files",
                str(session.run("MATCH (f:File) RETURN count(f) as c").single()["c"]),
            )
            table.add_row(
                "Functions",
                str(
                    session.run("MATCH (f:Function) RETURN count(f) as c").single()["c"]
                ),
            )
            table.add_row(
                "Classes",
                str(session.run("MATCH (c:Class) RETURN count(c) as c").single()["c"]),
            )
            table.add_row(
                "Modules",
                str(session.run("MATCH (m:Module) RETURN count(m) as c").single()["c"]),
            )
            api.console.print(table)
    except Exception as exc:
        api.console.print(f"[bold red]An error occurred:[/bold red] {exc}")
    finally:
        db_manager.close_driver()
