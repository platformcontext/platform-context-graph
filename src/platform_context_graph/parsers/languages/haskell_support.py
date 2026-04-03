"""Support constants and helper functions for the Haskell parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import re

from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

HASKELL_QUERIES = {
    "functions": """
        (function name: (variable) @name) @function_node
        (bind name: (variable) @name) @function_node
    """,
    "classes": """
        (data_type name: (name) @name) @class
        (class name: (name) @name) @class
        (newtype name: (name) @name) @class
    """,
    "imports": """
        (import) @import
    """,
    "calls": """
        (apply function: (variable) @name) @call_node
    """,
    "variables": """
        (bind name: (variable) @name) @variable
    """,
}


def _parse_classes(
    parser: Any, captures: list[tuple[Any, str]], source_code: str, path: Path
) -> list[dict[str, Any]]:
    """Parse Haskell type declarations (data, class, newtype).

    Args:
        parser: The parser instance owning the helper methods.
        captures: Query captures for type declarations.
        source_code: Raw source text for the file.
        path: File path being parsed.

    Returns:
        Parsed class-like declarations.
    """
    classes: list[dict[str, Any]] = []
    seen_nodes: set[tuple[int, int]] = set()

    for node, capture_name in captures:
        if capture_name == "name":
            class_node = node.parent
            if class_node is None:
                continue
            node_key = (class_node.start_byte, class_node.end_byte)
            if node_key in seen_nodes:
                continue
            seen_nodes.add(node_key)

            class_name = parser._get_node_text(node)
            node_type = class_node.type  # data_type, class, newtype

            classes.append(
                {
                    "name": class_name,
                    "line_number": class_node.start_point[0] + 1,
                    "end_line": class_node.end_point[0] + 1,
                    "type": node_type,
                    "bases": [],
                    "path": str(path),
                    "lang": parser.language_name,
                }
            )

    return classes


def _parse_variables(
    parser: Any, captures: list[tuple[Any, str]], source_code: str, path: Path
) -> list[dict[str, Any]]:
    """Parse Haskell top-level value bindings."""
    variables: list[dict[str, Any]] = []
    seen: set[int] = set()

    for node, capture_name in captures:
        if capture_name == "name":
            bind_node = node.parent
            if bind_node is None:
                continue
            key = bind_node.start_byte
            if key in seen:
                continue
            seen.add(key)

            variables.append(
                {
                    "name": parser._get_node_text(node),
                    "line_number": bind_node.start_point[0] + 1,
                    "path": str(path),
                    "lang": parser.language_name,
                    "context": None,
                    "class_context": None,
                }
            )

    return variables


def _parse_imports(
    parser: Any, captures: list[tuple[Any, str]], source_code: str
) -> list[dict[str, Any]]:
    """Parse Haskell import declarations."""
    imports: list[dict[str, Any]] = []

    for node, capture_name in captures:
        if capture_name != "import":
            continue
        try:
            text = parser._get_node_text(node)
            # Parse module name from text like:
            #   import Data.List (sort, nub)
            #   import qualified Data.Map as Map
            stripped = text.replace("import", "", 1).strip()
            is_qualified = stripped.startswith("qualified")
            if is_qualified:
                stripped = stripped.replace("qualified", "", 1).strip()

            # Split at first space, paren, or 'as'
            parts = re.split(r"[\s(]", stripped, maxsplit=1)
            module_name = parts[0].strip() if parts else stripped

            alias = None
            as_match = re.search(r"\bas\s+(\w+)", text)
            if as_match:
                alias = as_match.group(1)

            imports.append(
                {
                    "name": module_name,
                    "full_import_name": module_name,
                    "line_number": node.start_point[0] + 1,
                    "alias": alias,
                    "context": (None, None),
                    "lang": parser.language_name,
                    "is_dependency": False,
                }
            )
        except Exception:
            continue
    return imports


def _parse_calls(
    parser: Any,
    captures: list[tuple[Any, str]],
    source_code: str,
    path: Path,
    variables: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Parse Haskell function application expressions."""
    calls: list[dict[str, Any]] = []
    seen_calls: set[tuple[str, int]] = set()

    for node, capture_name in captures:
        if capture_name != "name":
            continue
        try:
            call_name = parser._get_node_text(node)
            start_line = node.start_point[0] + 1

            call_key = (call_name, start_line)
            if call_key in seen_calls:
                continue
            seen_calls.add(call_key)

            calls.append(
                {
                    "name": call_name,
                    "full_name": call_name,
                    "line_number": start_line,
                    "args": [],
                    "inferred_obj_type": None,
                    "context": [None, None, None],
                    "class_context": [None, None],
                    "lang": parser.language_name,
                    "is_dependency": False,
                }
            )
        except Exception:
            continue

    return calls


def pre_scan_haskell(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Build a name-to-file map for Haskell source files.

    Args:
        files: Haskell files to scan.
        parser_wrapper: Wrapper providing a parser instance.

    Returns:
        Mapping of discovered names to the files that define them.
    """
    imports_map: dict[str, list[str]] = {}
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()

            # Extract module name
            mod_match = re.search(r"^\s*module\s+([\w.]+)", content, re.MULTILINE)
            if mod_match:
                imports_map.setdefault(mod_match.group(1), []).append(str(path))

            # Extract top-level function/value names
            for match in re.finditer(r"^(\w+)\s+(?:::|=)", content, re.MULTILINE):
                name = match.group(1)
                if name not in (
                    "module",
                    "import",
                    "data",
                    "type",
                    "class",
                    "instance",
                    "where",
                    "let",
                    "in",
                    "do",
                    "if",
                    "then",
                    "else",
                    "case",
                    "of",
                ):
                    imports_map.setdefault(name, []).append(str(path))
        except Exception as exc:
            warning_logger(f"Tree-sitter pre-scan failed for {path}: {exc}")
    return imports_map
