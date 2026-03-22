"""Catalog and discovery helpers for registry bundles."""

from __future__ import annotations

from typing import Any

import requests
from rich.table import Table

from .common import MANIFEST_URL, REGISTRY_API_URL, console


def fetch_available_bundles() -> list[dict[str, Any]]:
    """Fetch bundle metadata from the public registry endpoints.

    Returns:
        A list of bundle metadata dictionaries. All discovered versions are
        preserved without deduplication.
    """
    all_bundles: list[dict[str, Any]] = []

    try:
        try:
            response = requests.get(MANIFEST_URL, timeout=10)
            if response.status_code == 200:
                manifest = response.json()
                if manifest.get("bundles"):
                    for bundle in manifest["bundles"]:
                        bundle["source"] = "on-demand"
                        if "bundle_name" in bundle:
                            bundle["full_name"] = bundle["bundle_name"].replace(
                                ".pcg",
                                "",
                            )
                        all_bundles.append(bundle)
        except Exception as exc:
            console.print(f"[dim]Note: Could not fetch on-demand bundles: {exc}[/dim]")

        try:
            response = requests.get(REGISTRY_API_URL, timeout=10)
            if response.status_code == 200:
                releases = response.json()
                weekly_releases = [
                    release
                    for release in releases
                    if release["tag_name"].startswith("bundles-")
                    and release["tag_name"] != "bundles-latest"
                ]

                if weekly_releases:
                    latest_weekly = weekly_releases[0]
                    for asset in latest_weekly.get("assets", []):
                        if asset["name"].endswith(".pcg"):
                            full_name = asset["name"].replace(".pcg", "")
                            name_parts = full_name.split("-")
                            all_bundles.append(
                                {
                                    "name": name_parts[0],
                                    "full_name": full_name,
                                    "repo": f"{name_parts[0]}/{name_parts[0]}",
                                    "bundle_name": asset["name"],
                                    "version": (
                                        name_parts[1]
                                        if len(name_parts) > 1
                                        else "latest"
                                    ),
                                    "commit": (
                                        name_parts[2]
                                        if len(name_parts) > 2
                                        else "unknown"
                                    ),
                                    "size": f"{asset['size'] / 1024 / 1024:.1f}MB",
                                    "download_url": asset["browser_download_url"],
                                    "generated_at": asset["updated_at"],
                                    "source": "weekly",
                                }
                            )
        except Exception as exc:
            console.print(f"[dim]Note: Could not fetch weekly bundles: {exc}[/dim]")

        for bundle in all_bundles:
            if "name" not in bundle:
                repo = bundle.get("repo", "")
                if "/" in repo:
                    bundle["name"] = repo.split("/")[-1]
                else:
                    full_name = bundle.get(
                        "full_name",
                        bundle.get("bundle_name", "unknown"),
                    )
                    bundle["name"] = full_name.split("-")[0]

            if "full_name" not in bundle:
                bundle["full_name"] = bundle.get(
                    "bundle_name",
                    bundle.get("name", "unknown"),
                ).replace(".pcg", "")

        return all_bundles
    except Exception as exc:
        console.print(f"[bold red]Error fetching bundles: {exc}[/bold red]")
        return []


def _get_base_package_name(bundle_name: str) -> str:
    """Extract the base package name from a bundle artifact name.

    Args:
        bundle_name: Bundle filename or full bundle identifier.

    Returns:
        The inferred base package name.
    """
    return bundle_name.replace(".pcg", "").split("-")[0]


def list_bundles(verbose: bool = False, unique: bool = False) -> None:
    """Display the available bundles in a Rich table.

    Args:
        verbose: Whether to include the download URL column.
        unique: Whether to keep only the latest version per package.
    """
    console.print("[cyan]Fetching available bundles...[/cyan]")
    bundles = fetch_available_bundles()

    if not bundles:
        console.print("[yellow]No bundles found in registry.[/yellow]")
        console.print("[dim]The registry may be empty or unreachable.[/dim]")
        return

    if unique:
        unique_bundles: dict[str, dict[str, Any]] = {}
        for bundle in bundles:
            base_name = bundle.get("name", "unknown")
            if base_name not in unique_bundles:
                unique_bundles[base_name] = bundle
                continue

            current_time = bundle.get("generated_at", "")
            existing_time = unique_bundles[base_name].get("generated_at", "")
            if current_time > existing_time:
                unique_bundles[base_name] = bundle
        bundles = list(unique_bundles.values())

    table = Table(
        show_header=True,
        header_style="bold magenta",
        title="Available Bundles",
    )
    table.add_column("Bundle Name", style="cyan", no_wrap=True)
    table.add_column("Repository", style="dim")
    table.add_column("Version", style="green")
    table.add_column("Size", justify="right")
    table.add_column("Source", style="yellow")
    if verbose:
        table.add_column("Download URL", style="blue", no_wrap=False)

    bundles.sort(
        key=lambda bundle: (bundle.get("name", ""), bundle.get("full_name", ""))
    )
    for bundle in bundles:
        display_name = bundle.get("full_name", bundle.get("name", "unknown"))
        row = [
            display_name,
            bundle.get("repo", "unknown"),
            bundle.get("version", bundle.get("tag", "latest")),
            bundle.get("size", "unknown"),
            bundle.get("source", "unknown"),
        ]
        if verbose:
            row.append(bundle.get("download_url", "N/A"))
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]Total bundles: {len(bundles)}[/dim]")
    if unique:
        console.print(
            "[dim]Showing only most recent version per package. Use without --unique to see all versions.[/dim]"
        )
    else:
        console.print("[dim]Use --unique to show only one version per package[/dim]")
    console.print("[dim]Use 'pcg registry download <name>' to download a bundle[/dim]")


def search_bundles(query: str) -> None:
    """Search the bundle catalog for a text query.

    Args:
        query: Search text matched against bundle names, repos, and descriptions.
    """
    console.print(f"[cyan]Searching for '{query}'...[/cyan]")
    bundles = fetch_available_bundles()

    if not bundles:
        console.print("[yellow]No bundles found in registry.[/yellow]")
        return

    query_lower = query.lower()
    matching_bundles = [
        bundle
        for bundle in bundles
        if query_lower in bundle.get("name", "").lower()
        or query_lower in bundle.get("repo", "").lower()
        or query_lower in bundle.get("description", "").lower()
    ]

    if not matching_bundles:
        console.print(f"[yellow]No bundles found matching '{query}'[/yellow]")
        console.print(
            "[dim]Try a different search term or use 'pcg registry list' to see all bundles[/dim]"
        )
        return

    table = Table(
        show_header=True,
        header_style="bold magenta",
        title=f"Search Results for '{query}'",
    )
    table.add_column("Name", style="cyan")
    table.add_column("Repository", style="dim")
    table.add_column("Version", style="green")
    table.add_column("Size", justify="right")

    for bundle in matching_bundles:
        table.add_row(
            bundle.get("name", "unknown"),
            bundle.get("repo", "unknown"),
            bundle.get("version", bundle.get("tag", "latest")),
            bundle.get("size", "unknown"),
        )

    console.print(table)
    console.print(f"\n[dim]Found {len(matching_bundles)} matching bundle(s)[/dim]")
