"""Runtime and root command registration for the CLI entrypoint."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import typer
from rich.table import Table

from ..remote import remote_mode_requested
from ..remote_commands import render_remote_workspace_status
from .runtime_admin import register_admin_commands


def register_runtime_commands(main_module: Any, app: typer.Typer) -> None:
    """Register runtime-oriented command groups on the root CLI app.

    Args:
        main_module: The imported ``platform_context_graph.cli.main`` module.
        app: The root Typer application.
    """
    mcp_app = typer.Typer(help="MCP client configuration commands")
    app.add_typer(mcp_app, name="mcp")

    api_app = typer.Typer(help="HTTP API server commands")
    app.add_typer(api_app, name="api")

    serve_app = typer.Typer(help="Combined service commands")
    app.add_typer(serve_app, name="serve")

    workspace_app = typer.Typer(
        help=(
            "Workspace discovery and materialization commands using the canonical "
            "source contract. Source modes: githubOrg, explicit, filesystem. "
            "Use PCG_REPOSITORY_RULES_JSON as the canonical selector."
        )
    )
    app.add_typer(workspace_app, name="workspace")

    admin_app = typer.Typer(help="Administrative local and remote operations")
    app.add_typer(admin_app, name="admin")
    register_admin_commands(main_module, admin_app)

    internal_app = typer.Typer(help="Internal runtime commands")
    app.add_typer(internal_app, name="internal")

    neo4j_app = typer.Typer(help="Neo4j database configuration commands")
    app.add_typer(neo4j_app, name="neo4j")

    @mcp_app.command("setup")
    def mcp_setup() -> None:
        """Configure IDE and CLI integrations for the MCP server."""
        main_module.console.print("\n[bold cyan]MCP Client Setup[/bold cyan]")
        main_module.console.print(
            "Configure your IDE or CLI tool to use PlatformContextGraph.\n"
        )
        main_module.configure_mcp_client()

    @mcp_app.command("start")
    def mcp_start(
        transport: str = typer.Option(
            "stdio",
            "--transport",
            "-t",
            help="Transport mode: stdio or sse",
            case_sensitive=False,
        ),
        host: str = typer.Option(
            "0.0.0.0",
            "--host",
            help="Host to bind SSE server (only used with --transport sse)",
        ),
        port: int = typer.Option(
            8080,
            "--port",
            "-p",
            help="Port for SSE server (only used with --transport sse)",
        ),
    ) -> None:
        """Start the PlatformContextGraph MCP server."""
        normalized_transport = transport.lower()
        if normalized_transport not in ("stdio", "sse"):
            raise typer.BadParameter(
                f"Unknown transport '{transport}'. Must be 'stdio' or 'sse'."
            )

        main_module.console.print(
            f"[bold green]Starting PlatformContextGraph Server ({normalized_transport} transport)...[/bold green]"
        )
        main_module._load_credentials()

        server = None
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            server = main_module.MCPServer(loop=loop)
            if normalized_transport == "sse":
                loop.run_until_complete(server.run_sse(host=host, port=port))
            else:
                loop.run_until_complete(server.run())
        except ValueError as exc:
            main_module.console.print(
                f"[bold red]Configuration Error:[/bold red] {exc}"
            )
            main_module.console.print(
                "Please run `pcg neo4j setup` or use FalkorDB (default)."
            )
        except KeyboardInterrupt:
            main_module.console.print(
                "\n[bold yellow]Server stopped by user.[/bold yellow]"
            )
        finally:
            if server:
                server.shutdown()
            loop.close()

    @mcp_app.command("tools")
    def mcp_tools() -> None:
        """List all available MCP tools."""
        main_module._load_credentials()
        main_module.console.print("[bold green]Available MCP Tools:[/bold green]")
        try:
            server = main_module.MCPServer()
            tools = server.tools.values()

            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Tool Name", style="dim", width=30)
            table.add_column("Description")

            for tool in sorted(tools, key=lambda item: item["name"]):
                table.add_row(tool["name"], tool["description"])

            main_module.console.print(table)
        except ValueError as exc:
            main_module.console.print(
                f"[bold red]Error loading tools:[/bold red] {exc}"
            )
            main_module.console.print(
                "Please ensure your database is configured correctly."
            )
        except Exception as exc:
            main_module.console.print(
                f"[bold red]An unexpected error occurred:[/bold red] {exc}"
            )

    @api_app.command("start")
    def api_start(
        host: str = typer.Option(
            "127.0.0.1", "--host", help="Host to bind the HTTP API server"
        ),
        port: int = typer.Option(
            8000, "--port", "-p", help="Port for the HTTP API server"
        ),
        reload: bool = typer.Option(
            False,
            "--reload/--no-reload",
            help="Enable Uvicorn auto-reload for development",
        ),
    ) -> None:
        """Start the PlatformContextGraph HTTP API server."""
        if main_module._console_output_enabled():
            main_module.console.print(
                "[bold green]Starting PlatformContextGraph HTTP API...[/bold green]"
            )
        main_module._load_credentials()
        main_module.start_http_api(host=host, port=port, reload=reload)

    @serve_app.command("start")
    def serve_start(
        host: str = typer.Option(
            "0.0.0.0", "--host", help="Host to bind the combined service"
        ),
        port: int = typer.Option(
            8080, "--port", "-p", help="Port for the combined service"
        ),
        reload: bool = typer.Option(
            False,
            "--reload/--no-reload",
            help="Enable Uvicorn auto-reload for development",
        ),
    ) -> None:
        """Start the combined MCP SSE and HTTP API service."""
        if main_module._console_output_enabled():
            main_module.console.print(
                "[bold green]Starting PlatformContextGraph service (HTTP API + MCP)...[/bold green]"
            )
        main_module._load_credentials()
        main_module.start_service(host=host, port=port, reload=reload)

    @workspace_app.command("plan")
    def workspace_plan() -> None:
        """Preview the repositories selected by the current workspace config."""

        main_module.workspace_plan_helper()

    @workspace_app.command("sync")
    def workspace_sync() -> None:
        """Clone, update, or copy the configured workspace without indexing."""

        main_module.workspace_sync_helper()

    @workspace_app.command("index")
    def workspace_index() -> None:
        """Index the configured materialized workspace."""

        main_module.workspace_index_helper()

    @workspace_app.command("status")
    def workspace_status(
        service_url: str | None = typer.Option(
            None,
            "--service-url",
            help="Base URL of the remote PlatformContextGraph HTTP service.",
        ),
        api_key: str | None = typer.Option(
            None,
            "--api-key",
            help="Bearer token for the remote PlatformContextGraph HTTP service.",
        ),
        profile: str | None = typer.Option(
            None,
            "--profile",
            help="Named remote profile used to resolve service URL and token.",
        ),
    ) -> None:
        """Show the configured workspace path and latest workspace index summary."""

        if remote_mode_requested(service_url, profile):
            render_remote_workspace_status(
                main_module,
                service_url=service_url,
                api_key=api_key,
                profile=profile,
            )
            return
        main_module.workspace_status_helper()

    @workspace_app.command("watch")
    def workspace_watch(
        include_repo: list[str] | None = typer.Option(
            None,
            "--include-repo",
            help="Repository glob(s) to include when watching the workspace.",
        ),
        exclude_repo: list[str] | None = typer.Option(
            None,
            "--exclude-repo",
            help="Repository glob(s) to exclude when watching the workspace.",
        ),
        sync_interval_seconds: int | None = typer.Option(
            None,
            "--sync-interval-seconds",
            help=(
                "Seconds between workspace rediscovery passes while watch is running. "
                "Useful when new repos are materialized under the workspace."
            ),
        ),
    ) -> None:
        """Watch the configured materialized workspace."""

        main_module.workspace_watch_helper(
            include_repositories=include_repo,
            exclude_repositories=exclude_repo,
            rediscover_interval_seconds=sync_interval_seconds,
        )

    @internal_app.command("bootstrap-index", hidden=True)
    def internal_bootstrap_index() -> None:
        """Run bootstrap clone and indexing once."""
        main_module.run_bootstrap_index(
            main_module.RepoSyncConfig.from_env(component="bootstrap-index")
        )

    @internal_app.command("repo-sync", hidden=True)
    def internal_repo_sync() -> None:
        """Run one repo sync cycle and re-index if needed."""
        main_module.run_repo_sync_cycle(
            main_module.RepoSyncConfig.from_env(component="repo-sync")
        )

    @internal_app.command("repo-sync-loop", hidden=True)
    def internal_repo_sync_loop(
        interval_seconds: int = typer.Option(
            None,
            "--interval-seconds",
            help="Seconds between repo sync cycles. Defaults to PCG_REPO_SYNC_INTERVAL_SECONDS or 900.",
        ),
    ) -> None:
        """Run the repo sync loop used by the sidecar container."""
        effective_interval = interval_seconds
        if effective_interval is None:
            effective_interval = int(os.getenv("PCG_REPO_SYNC_INTERVAL_SECONDS", "900"))
        main_module.run_repo_sync_loop(interval_seconds=effective_interval)

    @internal_app.command("resolution-engine", hidden=True)
    def internal_resolution_engine() -> None:
        """Run the standalone facts projection engine."""
        import asyncio
        from functools import partial

        from platform_context_graph.core import get_database_manager
        from platform_context_graph.core.jobs import JobManager
        from platform_context_graph.facts.state import (
            get_fact_store,
            get_fact_work_queue,
            get_projection_decision_store,
        )
        from platform_context_graph.resolution.orchestration import (
            project_work_item,
            start_resolution_engine,
        )
        from platform_context_graph.tools.graph_builder import GraphBuilder

        queue = get_fact_work_queue()
        if queue is None:
            raise typer.Exit(
                "Resolution engine requires PCG_POSTGRES_DSN or PCG_FACT_STORE_DSN"
            )
        fact_store = get_fact_store()
        decision_store = get_projection_decision_store()
        db_manager = get_database_manager()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        builder = GraphBuilder(db_manager, JobManager(), loop)
        projector = partial(
            project_work_item,
            builder=builder,
            fact_store=fact_store,
            decision_store=decision_store,
        )
        start_resolution_engine(queue=queue, projector=projector)

    @app.command("m", rich_help_panel="Shortcuts")
    def mcp_setup_alias() -> None:
        """Run the ``pcg mcp setup`` shortcut."""
        mcp_setup()

    @neo4j_app.command("setup")
    def neo4j_setup() -> None:
        """Configure the Neo4j database connection."""
        main_module.console.print("\n[bold cyan]Neo4j Database Setup[/bold cyan]")
        main_module.console.print(
            "Configure Neo4j database connection for PlatformContextGraph.\n"
        )
        main_module.run_neo4j_setup_wizard()

    @app.command("n", rich_help_panel="Shortcuts")
    def neo4j_setup_alias() -> None:
        """Run the ``pcg neo4j setup`` shortcut."""
        neo4j_setup()

    @app.command()
    def start() -> None:
        """Run the deprecated root ``start`` command."""
        main_module.console.print(
            "[yellow]⚠️  'pcg start' is deprecated. Use 'pcg mcp start' instead.[/yellow]"
        )
        mcp_start()

    @app.command()
    def help(ctx: typer.Context) -> None:
        """Show the main help message and exit."""
        root_ctx = ctx.parent or ctx
        typer.echo(root_ctx.get_help())

    @app.command("version")
    def version_cmd() -> None:
        """Show the installed application version."""
        main_module.console.print(
            f"PlatformContextGraph [bold cyan]{main_module.get_version()}[/bold cyan]"
        )

    @app.callback(invoke_without_command=True)
    def main(
        ctx: typer.Context,
        database: str | None = typer.Option(
            None,
            "--database",
            "-db",
            help="[Global] Temporarily override database backend (falkordb or neo4j) for any command",
        ),
        visual: bool = typer.Option(
            False,
            "--visual",
            "--viz",
            "-V",
            help="[Global] Show results as interactive graph visualization in browser",
        ),
        version_: bool = typer.Option(
            None,
            "--version",
            "-v",
            help="[Root-level only] Show version and exit",
            is_eager=True,
        ),
        help_: bool = typer.Option(
            None,
            "--help",
            "-h",
            help="[Root-level only] Show help and exit",
            is_eager=True,
        ),
    ) -> None:
        """Initialize global CLI state and show the welcome text when idle."""
        del help_
        ctx.ensure_object(dict)

        if database:
            os.environ["PCG_RUNTIME_DB_TYPE"] = database

        if visual:
            ctx.obj["visual"] = True

        if version_:
            main_module.console.print(
                f"PlatformContextGraph [bold cyan]{main_module.get_version()}[/bold cyan]"
            )
            raise typer.Exit()

        if ctx.invoked_subcommand is None:
            main_module.console.print(
                "[bold green]👋 Welcome to PlatformContextGraph (pcg)![/bold green]\n"
            )
            main_module.console.print(
                "PlatformContextGraph is both an [bold cyan]MCP server[/bold cyan] and a [bold cyan]CLI toolkit[/bold cyan] for code analysis.\n"
            )
            main_module.console.print(
                "🤖 [bold]For MCP Server Mode (AI assistants):[/bold]"
            )
            main_module.console.print(
                "   1. Run [cyan]pcg mcp setup[/cyan] (or [cyan]pcg m[/cyan]) to configure your IDE"
            )
            main_module.console.print(
                "   2. Run [cyan]pcg mcp start[/cyan] to launch the server\n"
            )
            main_module.console.print(
                "🛠️  [bold]For CLI Toolkit Mode (direct usage):[/bold]"
            )
            main_module.console.print(
                "   • [cyan]pcg index .[/cyan] - Index your current directory"
            )
            main_module.console.print(
                "   • [cyan]pcg list[/cyan] - List indexed repositories\n"
            )
            main_module.console.print(
                "📊 [bold]Using Neo4j instead of FalkorDB?[/bold]"
            )
            main_module.console.print(
                "     Run [cyan]pcg neo4j setup[/cyan] (or [cyan]pcg n[/cyan]) to configure Neo4j\n"
            )
            main_module.console.print("📈 [bold]Want visual graph output?[/bold]")
            main_module.console.print(
                "     Add [cyan]-V[/cyan] or [cyan]--visual[/cyan] to any analyze/find command\n"
            )
            main_module.console.print(
                "👉 Run [cyan]pcg help[/cyan] to see all available commands"
            )
            main_module.console.print(
                "👉 Run [cyan]pcg --version[/cyan] to check the version"
            )
