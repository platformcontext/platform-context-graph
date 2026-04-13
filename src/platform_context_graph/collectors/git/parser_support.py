"""Go-aligned parser support metadata for Python-side discovery helpers."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS = frozenset(
    {
        ".c",
        ".cc",
        ".cfg",
        ".cnf",
        ".conf",
        ".cpp",
        ".cs",
        ".csx",
        ".cts",
        ".cxx",
        ".dart",
        ".ex",
        ".exs",
        ".go",
        ".groovy",
        ".h",
        ".hcl",
        ".hh",
        ".hpp",
        ".hs",
        ".ipynb",
        ".j2",
        ".java",
        ".jinja",
        ".jinja2",
        ".js",
        ".json",
        ".jsx",
        ".kt",
        ".mjs",
        ".mts",
        ".php",
        ".pl",
        ".pm",
        ".py",
        ".pyw",
        ".rb",
        ".rs",
        ".scala",
        ".sql",
        ".swift",
        ".tf",
        ".tftpl",
        ".tpl",
        ".ts",
        ".tsx",
        ".yaml",
        ".yml",
    }
)
SUPPORTED_EXACT_FILENAMES = frozenset({"dockerfile", "jenkinsfile"})
SUPPORTED_PREFIX_FILENAMES = ("dockerfile.", "jenkinsfile.")


def supports_path(path: Path) -> bool:
    """Return whether Go-owned parser metadata supports one path."""

    name = path.name.lower()
    if name in SUPPORTED_EXACT_FILENAMES:
        return True
    if any(name.startswith(prefix) for prefix in SUPPORTED_PREFIX_FILENAMES):
        return True
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


__all__ = [
    "SUPPORTED_EXACT_FILENAMES",
    "SUPPORTED_EXTENSIONS",
    "SUPPORTED_PREFIX_FILENAMES",
    "supports_path",
]
