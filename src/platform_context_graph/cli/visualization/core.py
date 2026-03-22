"""Core utilities for CLI graph visualizations."""

from __future__ import annotations

import html
import json
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from ...paths import get_app_home

console = Console(stderr=True)


def escape_html(text: Any) -> str:
    """Escape HTML special characters for safe rendering.

    Args:
        text: Value to escape.

    Returns:
        A string safe to embed into HTML text content.
    """
    if text is None:
        return ""
    return html.escape(str(text))


def get_visualization_dir() -> Path:
    """Return the directory used for generated visualization files.

    Returns:
        The visualization output directory, creating it when needed.
    """
    viz_dir = get_app_home() / "visualizations"
    viz_dir.mkdir(parents=True, exist_ok=True)
    return viz_dir


def generate_filename(prefix: str = "pcg_viz") -> str:
    """Generate a unique visualization filename.

    Args:
        prefix: Filename prefix to use for the generated artifact.

    Returns:
        A unique HTML filename.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique = uuid.uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{unique}.html"


def _json_for_inline_script(data: Any) -> str:
    """Serialize JSON for safe embedding inside a ``<script>`` tag.

    Args:
        data: Object to serialize.

    Returns:
        A JSON string with script-breaking sequences escaped.
    """
    raw = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    raw = raw.replace("</", "<\\/")
    raw = raw.replace("<!--", "<\\!--")
    return raw.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def get_node_color(node_type: str) -> dict[str, Any]:
    """Return the color palette for a visualization node type.

    Args:
        node_type: Semantic node type used in the visualization.

    Returns:
        A vis-network compatible color configuration.
    """
    colors = {
        "Function": {
            "background": "#D1FAE5",
            "border": "#10B981",
            "highlight": "#34D399",
        },
        "Class": {
            "background": "#DBEAFE",
            "border": "#3B82F6",
            "highlight": "#60A5FA",
        },
        "Module": {
            "background": "#F3E8FF",
            "border": "#A855F7",
            "highlight": "#C084FC",
        },
        "File": {
            "background": "#E0E7FF",
            "border": "#6366F1",
            "highlight": "#818CF8",
        },
        "Repository": {
            "background": "#FFE4E6",
            "border": "#F43F5E",
            "highlight": "#FB7185",
        },
        "Package": {
            "background": "#F1F5F9",
            "border": "#64748B",
            "highlight": "#94A3B8",
        },
        "Variable": {
            "background": "#FEF3C7",
            "border": "#F59E0B",
            "highlight": "#FBBF24",
        },
        "Caller": {
            "background": "#CFFAFE",
            "border": "#06B6D4",
            "highlight": "#22D3EE",
        },
        "Callee": {
            "background": "#ECFDF5",
            "border": "#10B981",
            "highlight": "#34D399",
        },
        "Target": {
            "background": "#FEE2E2",
            "border": "#EF4444",
            "highlight": "#F87171",
        },
        "Source": {
            "background": "#E0F2FE",
            "border": "#0EA5E9",
            "highlight": "#38BDF8",
        },
        "Parent": {
            "background": "#FFEDD5",
            "border": "#F97316",
            "highlight": "#FB923C",
        },
        "Child": {
            "background": "#F0FDFA",
            "border": "#14B8A6",
            "highlight": "#2DD4BF",
        },
        "Override": {
            "background": "#EDE9FE",
            "border": "#8B5CF6",
            "highlight": "#A78BFA",
        },
        "default": {
            "background": "#F1F5F9",
            "border": "#94A3B8",
            "highlight": "#CBD5E1",
        },
    }
    config = colors.get(node_type, colors["default"])
    return {
        "background": config["background"],
        "border": config["border"],
        "highlight": {
            "background": config["highlight"],
            "border": config["border"],
        },
        "hover": {
            "background": config["highlight"],
            "border": config["border"],
        },
    }


def _safe_json_dumps(obj: Any, indent: int = 2) -> str:
    """Serialize a JSON object while tolerating unknown value types.

    Args:
        obj: Object to serialize.
        indent: Indentation passed to ``json.dumps``.

    Returns:
        A JSON string, or ``"{}"`` when serialization fails.
    """

    def default_handler(value: Any) -> str:
        """Convert unsupported JSON values into printable strings."""
        try:
            return str(value)
        except Exception:
            return "<non-serializable>"

    try:
        return json.dumps(obj, indent=indent, default=default_handler)
    except Exception:
        return "{}"


def save_and_open_visualization(
    html_content: str,
    prefix: str = "pcg_viz",
) -> str | None:
    """Persist a visualization to disk and open it in the default browser.

    Args:
        html_content: Complete HTML document to write.
        prefix: Filename prefix for the generated file.

    Returns:
        The saved file path as a string, or ``None`` when saving fails.
    """
    viz_dir = get_visualization_dir()
    filepath = viz_dir / generate_filename(prefix)

    try:
        with open(filepath, "w", encoding="utf-8") as handle:
            handle.write(html_content)
    except (IOError, OSError) as exc:
        console.print(f"[red]Error saving visualization: {exc}[/red]")
        return None

    console.print(f"[green]✓ Visualization saved:[/green] {filepath}")
    console.print("[dim]Opening in browser...[/dim]")
    try:
        webbrowser.open(filepath.as_uri())
    except Exception as exc:
        console.print(f"[yellow]Could not open browser automatically: {exc}[/yellow]")
        console.print(f"[dim]Open this file manually: {filepath}[/dim]")

    return str(filepath)


def check_visual_flag(ctx: Any, local_visual: bool = False) -> bool:
    """Check whether visualization mode is enabled.

    Args:
        ctx: Typer context object.
        local_visual: Local ``--visual`` flag value.

    Returns:
        ``True`` when either the local or global visual flag is enabled.
    """
    global_visual = False
    if ctx and hasattr(ctx, "obj") and ctx.obj:
        global_visual = ctx.obj.get("visual", False)
    return local_visual or global_visual
