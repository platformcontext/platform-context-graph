"""Download and load workflows for registry bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...core.pcg_bundle import PCGBundle
from ..cli_helpers import _initialize_services
from .catalog import fetch_available_bundles
from .common import GITHUB_ORG, GITHUB_REPO, console


def download_bundle(
    name: str,
    output_dir: str | None = None,
    auto_load: bool = False,
):
    """Download a bundle from the registry.

    Args:
        name: Full bundle name or base package name.
        output_dir: Optional target directory for the downloaded file.
        auto_load: Whether the caller intends to load the downloaded file
            immediately.

    Returns:
        The downloaded file path when ``auto_load`` is true and the bundle is
        ready to load. Otherwise returns ``None``.

    Raises:
        typer.Exit: If the bundle cannot be located or downloaded.
    """
    console.print(f"[cyan]Looking for bundle '{name}'...[/cyan]")
    bundles = fetch_available_bundles()

    if not bundles:
        console.print("[bold red]Could not fetch bundle registry.[/bold red]")
        raise typer.Exit(code=1)

    bundle = next(
        (
            bundle
            for bundle in bundles
            if bundle.get("full_name", "").lower() == name.lower()
        ),
        None,
    )
    if bundle:
        console.print(f"[dim]Found exact match: {bundle.get('full_name')}[/dim]")

    if not bundle:
        matching_bundles = [
            bundle
            for bundle in bundles
            if bundle.get("name", "").lower() == name.lower()
        ]
        if matching_bundles:
            matching_bundles.sort(
                key=lambda bundle: bundle.get("generated_at", ""),
                reverse=True,
            )
            bundle = matching_bundles[0]
            console.print(
                f"[yellow]Multiple versions found for '{name}'. Using most recent:[/yellow]"
            )
            console.print(f"[cyan]  → {bundle.get('full_name')}[/cyan]")

            if len(matching_bundles) > 1:
                console.print("\n[dim]Other available versions:[/dim]")
                for alternative in matching_bundles[1:4]:
                    console.print(f"[dim]  • {alternative.get('full_name')}[/dim]")
                if len(matching_bundles) > 4:
                    console.print(
                        f"[dim]  ... and {len(matching_bundles) - 4} more[/dim]"
                    )
                console.print()

    if not bundle:
        suggestions = []
        name_lower = name.lower()
        for candidate in bundles:
            base_name = candidate.get("name", "").lower()
            full_name = candidate.get("full_name", "").lower()
            if name_lower in base_name or name_lower in full_name:
                suggestions.append(
                    candidate.get("full_name", candidate.get("name", "unknown"))
                )

        console.print(f"[bold red]Bundle '{name}' not found in registry.[/bold red]")
        if suggestions:
            console.print("\n[yellow]Did you mean one of these?[/yellow]")
            for suggestion in suggestions[:5]:
                console.print(f"  • {suggestion}")
        console.print(
            "\n[dim]Use 'pcg registry list' to see all available bundles[/dim]"
        )
        raise typer.Exit(code=1)

    download_url = bundle.get("download_url")
    if not download_url:
        console.print(f"[bold red]No download URL found for bundle '{name}'[/bold red]")
        raise typer.Exit(code=1)

    bundle_filename = bundle.get("bundle_name", f"{name}.pcg")
    if output_dir:
        output_path = Path(output_dir) / bundle_filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path = Path.cwd() / bundle_filename

    if output_path.exists():
        console.print(f"[yellow]Bundle already exists: {output_path}[/yellow]")
        if not typer.confirm("Overwrite?", default=False):
            console.print("[yellow]Download cancelled[/yellow]")
            if auto_load:
                console.print("[cyan]Using existing bundle for loading...[/cyan]")
                return str(output_path)
            return None
        output_path.unlink()

    try:
        console.print(f"[cyan]Downloading {bundle_filename}...[/cyan]")
        console.print(f"[dim]From: {download_url}[/dim]")
        response = requests.get(download_url, stream=True, timeout=30)
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Downloading {bundle.get('size', 'unknown')}...",
                total=total_size,
            )
            with open(output_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
                        progress.update(task, advance=len(chunk))

        console.print(
            f"[bold green]✓ Downloaded successfully: {output_path}[/bold green]"
        )
        if auto_load:
            return str(output_path)

        console.print(f"[dim]Load with: pcg load {output_path}[/dim]")
        return None
    except requests.exceptions.RequestException as exc:
        console.print(f"[bold red]Download failed: {exc}[/bold red]")
        if output_path.exists():
            output_path.unlink()
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Error: {exc}[/bold red]")
        if output_path.exists():
            output_path.unlink()
        raise typer.Exit(code=1)


def request_bundle(repo_url: str, wait: bool = False) -> None:
    """Explain the current on-demand bundle generation workflow.

    Args:
        repo_url: GitHub repository URL for the requested bundle.
        wait: Whether the CLI caller asked to wait for bundle completion.

    Raises:
        typer.Exit: If ``repo_url`` is not a valid GitHub repository URL.
    """
    console.print(f"[cyan]Requesting bundle generation for: {repo_url}[/cyan]")
    if not repo_url.startswith("https://github.com/"):
        console.print(
            "[bold red]Invalid GitHub URL. Must start with 'https://github.com/'[/bold red]"
        )
        raise typer.Exit(code=1)

    console.print(
        "\n[yellow]Note: Bundle generation requires GitHub authentication.[/yellow]"
    )
    console.print("[cyan]Please use one of these methods:[/cyan]\n")
    console.print("1. [bold]Via GitHub Actions:[/bold]")
    console.print(f"   Go to: https://github.com/{GITHUB_ORG}/{GITHUB_REPO}/actions")
    console.print("   Select: 'Generate Bundle On-Demand'")
    console.print("   Click: 'Run workflow'")
    console.print(f"   Enter: {repo_url}\n")
    console.print("2. [bold]Via the project docs and repo guidance:[/bold]")
    console.print(f"   Read: https://github.com/{GITHUB_ORG}/{GITHUB_REPO}")
    console.print("   Follow the current bundle request workflow documented there\n")
    console.print("[dim]Bundle generation typically takes 5-10 minutes.[/dim]")
    console.print("[dim]Use 'pcg registry list' to check when it's available.[/dim]")

    if wait:
        console.print("\n[yellow]Note: Automatic waiting not yet implemented.[/yellow]")
        console.print(
            "[dim]Please check back in 5-10 minutes and use "
            "'pcg registry download <name>'[/dim]"
        )


def load_bundle_command(
    bundle_name: str,
    clear_existing: bool = False,
) -> tuple[bool, str, dict[str, Any]]:
    """Download a bundle if needed and import it into the active database.

    Args:
        bundle_name: Bundle file path or registry bundle name.
        clear_existing: Whether existing graph data should be cleared first.

    Returns:
        A tuple of ``(success, message, stats)`` summarizing the load outcome.
    """
    db_manager = None
    try:
        services = _initialize_services()
        if not all(services):
            return False, "Failed to initialize database services", {}

        db_manager, _, _ = services
        bundle_path = Path(bundle_name)
        if not bundle_path.exists():
            try:
                download_bundle(bundle_name, output_dir=None, auto_load=False)
                if not bundle_path.exists():
                    bundle_path = Path(f"{bundle_name}.pcg")
                    if not bundle_path.exists():
                        return False, f"Bundle not found: {bundle_name}", {}
            except Exception as exc:
                return False, f"Failed to download bundle: {exc}", {}

        bundle = PCGBundle(db_manager)
        success, message = bundle.import_from_bundle(
            bundle_path=bundle_path,
            clear_existing=clear_existing,
        )
        if not success:
            return False, message, {}

        stats: dict[str, Any] = {}
        if "Nodes:" in message and "Edges:" in message:
            try:
                for part in message.split("|"):
                    if "Nodes:" in part:
                        stats["nodes"] = int(
                            part.split(":")[1].strip().replace(",", "")
                        )
                    elif "Edges:" in part:
                        stats["edges"] = int(
                            part.split(":")[1].strip().replace(",", "")
                        )
            except Exception:
                pass

        return True, message, stats
    except Exception as exc:
        return False, f"Error loading bundle: {exc}", {}
    finally:
        if db_manager is not None:
            db_manager.close_driver()
