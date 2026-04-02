"""Bundle and registry command registration for the CLI entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from ..remote import RemoteAPIError, request_json, resolve_remote_target


def register_bundle_registry_commands(main_module: Any, app: typer.Typer) -> None:
    """Register bundle and registry commands on the root CLI app.

    Args:
        main_module: The imported ``platform_context_graph.cli.main`` module.
        app: The root Typer application.
    """
    bundle_app = typer.Typer(help="Create and load pre-indexed graph bundles")
    app.add_typer(bundle_app, name="bundle")

    registry_app = typer.Typer(help="Browse and download bundles from the registry")
    app.add_typer(registry_app, name="registry")

    @bundle_app.command("export")
    def bundle_export(
        output: str = typer.Argument(..., help="Output path for the .pcg bundle file"),
        repo: str | None = typer.Option(
            None,
            "--repo",
            "-r",
            help="Specific repository path to export (default: export all)",
        ),
        no_stats: bool = typer.Option(
            False, "--no-stats", help="Skip statistics generation"
        ),
    ) -> None:
        """Export the current graph to a portable ``.pcg`` bundle."""
        main_module._load_credentials()
        from platform_context_graph.core.pcg_bundle import PCGBundle

        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, _ = services

        try:
            output_path = Path(output)
            repo_path = Path(repo).resolve() if repo else None

            main_module.console.print(
                f"[cyan]Exporting graph to {output_path}...[/cyan]"
            )
            if repo_path:
                main_module.console.print(f"[dim]Repository: {repo_path}[/dim]")
            else:
                main_module.console.print("[dim]Exporting all repositories[/dim]")

            bundle = PCGBundle(db_manager)
            success, message = bundle.export_to_bundle(
                output_path, repo_path=repo_path, include_stats=not no_stats
            )

            if success:
                main_module.console.print(f"[bold green]{message}[/bold green]")
            else:
                main_module.console.print(
                    f"[bold red]Export failed: {message}[/bold red]"
                )
                raise typer.Exit(code=1)
        finally:
            db_manager.close_driver()

    @bundle_app.command("import")
    def bundle_import(
        bundle_file: str = typer.Argument(
            ..., help="Path to the .pcg bundle file to import"
        ),
        clear: bool = typer.Option(
            False, "--clear", help="Clear existing graph data before importing"
        ),
    ) -> None:
        """Import a ``.pcg`` bundle into the current database."""
        main_module._load_credentials()
        from platform_context_graph.core.pcg_bundle import PCGBundle

        services = main_module._initialize_services()
        if not all(services):
            return
        db_manager, _, _ = services

        try:
            bundle_path = Path(bundle_file)
            if not bundle_path.exists():
                main_module.console.print(
                    f"[bold red]Bundle file not found: {bundle_path}[/bold red]"
                )
                raise typer.Exit(code=1)

            if clear:
                main_module.console.print(
                    "[yellow]⚠️  Warning: This will clear all existing graph data![/yellow]"
                )
                if not typer.confirm(
                    "Are you sure you want to continue?", default=False
                ):
                    main_module.console.print("[yellow]Import cancelled[/yellow]")
                    return

            main_module.console.print(
                f"[cyan]Importing bundle from {bundle_path}...[/cyan]"
            )

            bundle = PCGBundle(db_manager)
            success, message = bundle.import_from_bundle(
                bundle_path, clear_existing=clear
            )
            if success:
                main_module.console.print(f"[bold green]{message}[/bold green]")
            else:
                main_module.console.print(
                    f"[bold red]Import failed: {message}[/bold red]"
                )
                raise typer.Exit(code=1)
        finally:
            db_manager.close_driver()

    @bundle_app.command("load")
    def bundle_load(
        bundle_name: str = typer.Argument(
            ..., help="Bundle name or path to load (e.g., 'numpy' or 'numpy.pcg')"
        ),
        clear: bool = typer.Option(
            False, "--clear", help="Clear existing graph data before loading"
        ),
    ) -> None:
        """Load a pre-indexed bundle, downloading it first when needed."""
        main_module._load_credentials()

        bundle_path = Path(bundle_name)
        if bundle_path.is_absolute() or (
            bundle_path.suffix == ".pcg" and bundle_path.exists()
        ):
            bundle_import(str(bundle_path), clear=clear)
            return

        if not bundle_path.suffix:
            bundle_path = Path(f"{bundle_name}.pcg")

        if bundle_path.exists():
            main_module.console.print(f"[dim]Found local bundle: {bundle_path}[/dim]")
            bundle_import(str(bundle_path), clear=clear)
            return

        main_module.console.print(
            f"[yellow]Bundle '{bundle_name}' not found locally.[/yellow]"
        )
        main_module.console.print(
            "[cyan]Attempting to download from registry...[/cyan]"
        )

        try:
            from ..registry_commands import download_bundle

            name = bundle_path.stem
            downloaded_path = download_bundle(name, output_dir=None, auto_load=True)
            if downloaded_path:
                bundle_import(downloaded_path, clear=clear)
            else:
                main_module.console.print(
                    f"[bold red]Failed to download bundle '{name}'[/bold red]"
                )
                raise typer.Exit(code=1)
        except Exception as exc:
            main_module.console.print(f"[bold red]Error: {exc}[/bold red]")
            main_module.console.print(
                "[dim]Use 'pcg registry list' to see available bundles[/dim]"
            )
            raise typer.Exit(code=1)

    @bundle_app.command("upload")
    def bundle_upload(
        bundle_file: str = typer.Argument(
            ..., help="Path to the .pcg bundle file to upload"
        ),
        service_url: str = typer.Option(
            None,
            "--service-url",
            help="Base URL of the PlatformContextGraph HTTP service",
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
        clear: bool = typer.Option(
            False,
            "--clear",
            help="Clear existing graph data before importing the uploaded bundle",
        ),
        timeout_seconds: int = typer.Option(
            1800,
            "--timeout-seconds",
            min=1,
            help="HTTP read timeout for the remote bundle import request.",
        ),
    ) -> None:
        """Upload a ``.pcg`` bundle to a remote PlatformContextGraph service."""

        bundle_path = Path(bundle_file)
        if not bundle_path.exists():
            main_module.console.print(
                f"[bold red]Bundle file not found: {bundle_path}[/bold red]"
            )
            raise typer.Exit(code=1)

        remote_target = resolve_remote_target(
            service_url=service_url,
            api_key=api_key,
            profile=profile,
            timeout_seconds=timeout_seconds,
            require_remote=True,
        )
        url = f"{remote_target.service_url}/api/v0/bundles/import"
        main_module.console.print(f"[cyan]Uploading bundle to {url}...[/cyan]")

        try:
            with bundle_path.open("rb") as handle:
                payload = request_json(
                    remote_target,
                    method="POST",
                    path="/api/v0/bundles/import",
                    files={
                        "bundle": (
                            bundle_path.name,
                            handle,
                            "application/octet-stream",
                        )
                    },
                    data={"clear_existing": "true" if clear else "false"},
                    timeout_seconds=timeout_seconds,
                )
        except RemoteAPIError as exc:
            main_module.console.print(f"[bold red]Upload failed: {exc}[/bold red]")
            raise typer.Exit(code=1) from exc

        if not payload.get("success"):
            main_module.console.print(
                f"[bold red]Import failed: {payload.get('message', 'unknown error')}[/bold red]"
            )
            raise typer.Exit(code=1)

        typer.echo(payload.get("message", "Bundle imported"))

    @app.command("export", rich_help_panel="Bundle Shortcuts")
    def export_shortcut(
        output: str = typer.Argument(..., help="Output path for the .pcg bundle file"),
        repo: str | None = typer.Option(
            None, "--repo", "-r", help="Specific repository path to export"
        ),
    ) -> None:
        """Run the ``pcg bundle export`` shortcut."""
        bundle_export(output, repo, False)

    @app.command("load", rich_help_panel="Bundle Shortcuts")
    def load_shortcut(
        bundle_name: str = typer.Argument(..., help="Bundle name or path to load"),
        clear: bool = typer.Option(
            False, "--clear", help="Clear existing graph data before loading"
        ),
    ) -> None:
        """Run the ``pcg bundle load`` shortcut."""
        bundle_load(bundle_name, clear)

    @registry_app.command("list")
    def registry_list(
        verbose: bool = typer.Option(
            False,
            "--verbose",
            "-v",
            help="Show detailed information including download URLs",
        ),
        unique: bool = typer.Option(
            False,
            "--unique",
            "-u",
            help="Show only one version per package (most recent)",
        ),
    ) -> None:
        """List all available bundles in the registry."""
        from ..registry_commands import list_bundles

        list_bundles(verbose=verbose, unique=unique)

    @registry_app.command("search")
    def registry_search(
        query: str = typer.Argument(
            ..., help="Search query (matches name, repository, or description)"
        )
    ) -> None:
        """Search for bundles in the registry."""
        from ..registry_commands import search_bundles

        search_bundles(query)

    @registry_app.command("download")
    def registry_download(
        name: str = typer.Argument(..., help="Bundle name to download (e.g., 'numpy')"),
        output_dir: str | None = typer.Option(
            None,
            "--output",
            "-o",
            help="Output directory (default: current directory)",
        ),
        load: bool = typer.Option(
            False,
            "--load",
            "-l",
            help="Automatically load the bundle after downloading",
        ),
    ) -> None:
        """Download a bundle from the registry."""
        from ..registry_commands import download_bundle

        bundle_path = download_bundle(name, output_dir, auto_load=load)
        if load and bundle_path:
            main_module.console.print("\n[cyan]Loading bundle...[/cyan]")
            bundle_import(bundle_path, clear=False)

    @registry_app.command("request")
    def registry_request(
        repo_url: str = typer.Argument(..., help="GitHub repository URL to index"),
        wait: bool = typer.Option(
            False,
            "--wait",
            "-w",
            help="Wait for generation to complete (not yet implemented)",
        ),
    ) -> None:
        """Request on-demand generation of a bundle."""
        from ..registry_commands import request_bundle

        request_bundle(repo_url, wait=wait)
