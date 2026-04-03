"""C# tree-sitter parser compatibility facade."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

from platform_context_graph.utils.debug_log import error_logger

from .csharp_support import parse_csharp_file


class CSharpTreeSitterParser:
    """Parse C# source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Initialize the parser facade.

        Args:
            generic_parser_wrapper: Wrapper object providing parser and language.
        """
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "c_sharp"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def parse(
        self, path: Path, is_dependency: bool = False, index_source: bool = False
    ) -> Dict[str, Any]:
        """Parse one C# file."""
        return parse_csharp_file(
            self, path, is_dependency=is_dependency, index_source=index_source
        )


def pre_scan_csharp(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Pre-scan C# files to map top-level names to file paths."""
    name_to_files: dict[str, list[str]] = {}

    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()

            for match in re.finditer(
                r"\b(?:public\s+|private\s+|protected\s+|internal\s+)?(?:static\s+)?(?:abstract\s+)?(?:sealed\s+)?(?:partial\s+)?class\s+(\w+)",
                content,
            ):
                name_to_files.setdefault(match.group(1), []).append(str(path))

            for match in re.finditer(
                r"\b(?:public\s+|private\s+|protected\s+|internal\s+)?(?:partial\s+)?interface\s+(\w+)",
                content,
            ):
                name_to_files.setdefault(match.group(1), []).append(str(path))

            for match in re.finditer(
                r"\b(?:public\s+|private\s+|protected\s+|internal\s+)?(?:readonly\s+)?(?:partial\s+)?struct\s+(\w+)",
                content,
            ):
                name_to_files.setdefault(match.group(1), []).append(str(path))

            for match in re.finditer(
                r"\b(?:public\s+|private\s+|protected\s+|internal\s+)?(?:sealed\s+)?record\s+(?:class\s+)?(\w+)",
                content,
            ):
                name_to_files.setdefault(match.group(1), []).append(str(path))
        except Exception as exc:
            error_logger(f"Error pre-scanning C# file {path}: {exc}")

    del parser_wrapper
    return name_to_files


def _empty_result(path: Path, is_dependency: bool) -> dict[str, Any]:
    """Return the standard empty parse payload for C# files."""
    return {
        "path": str(path),
        "functions": [],
        "classes": [],
        "interfaces": [],
        "structs": [],
        "enums": [],
        "records": [],
        "properties": [],
        "variables": [],
        "imports": [],
        "function_calls": [],
        "is_dependency": is_dependency,
        "lang": "c_sharp",
    }


__all__ = ["CSharpTreeSitterParser", "pre_scan_csharp"]
