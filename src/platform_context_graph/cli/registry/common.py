"""Shared constants and console helpers for registry commands."""

from __future__ import annotations

from rich.console import Console

console = Console()

GITHUB_ORG = "platformcontext"
GITHUB_REPO = "platform-context-graph"
REGISTRY_API_URL = f"https://api.github.com/repos/{GITHUB_ORG}/{GITHUB_REPO}/releases"
MANIFEST_URL = (
    "https://github.com/"
    f"{GITHUB_ORG}/{GITHUB_REPO}/releases/download/on-demand-bundles/manifest.json"
)
