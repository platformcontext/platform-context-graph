"""Support constants and helper functions for the Haskell parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import re

from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

HASKELL_QUERIES = {
    "functions": """
        [
        (function_declaration
            name: (simple_identifier) @name
            parameters: (parameters)* @params
        ) @function_node
        (init_declaration
            parameters: (parameter)* @params
        ) @init_node
        ]
    """,
    "classes": """
    [
        (class_declaration
            name: (type_identifier) @name
        ) @class
        (
        struct_declaration
            name: (type_identifier) @name
        ) @struct
        (
            enum_declaration
            name: (type_identifier) @name
        ) @enum
        (
            protocol_declaration
            name: (type_identifier) @name
        ) @protocol
    ]
    """,
    "imports": """
        (import_declaration) @import
    """,
    "calls": """
        (call_expression) @call_node
    """,
    "variables": """
        (property_declaration
            (variable_declaration
                (simple_identifier) @name
            )
        ) @variable
    """,
}


def _parse_classes(
    parser: Any, captures: list[tuple[Any, str]], source_code: str, path: Path
) -> list[dict[str, Any]]:
    """Parse Haskell-like type declarations.

    Args:
        parser: The parser instance owning the helper methods.
        captures: Query captures for type declarations.
        source_code: Raw source text for the file.
        path: File path being parsed.

    Returns:
        Parsed class-like declarations.
    """
    classes: list[dict[str, Any]] = []
    seen_nodes: set[tuple[int, int, str]] = set()

    for node, capture_name in captures:
        if capture_name != "class":
            continue
        node_id = (node.start_byte, node.end_byte, node.type)
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)

        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            class_name = "Anonymous"
            if node.type == "companion_object":
                class_name = "Companion"

            for child in node.children:
                if child.type in ("type_identifier", "simple_identifier"):
                    class_name = parser._get_node_text(child)
                    break

            bases: list[str] = []
            for child in node.children:
                if child.type == "delegation_specifier":
                    for specifier in child.children:
                        if specifier.type == "constructor_invocation":
                            for sub in specifier.children:
                                if sub.type == "user_type":
                                    bases.append(parser._get_node_text(sub))
                        elif specifier.type == "user_type":
                            bases.append(parser._get_node_text(specifier))

            class_data = {
                "name": class_name,
                "line_number": start_line,
                "end_line": end_line,
                "bases": bases,
                "path": str(path),
                "lang": parser.language_name,
            }
            if parser.index_source:
                class_data["source"] = parser._get_node_text(node)
            classes.append(class_data)
        except Exception as exc:
            error_logger(f"Error parsing class in {path}: {exc}")

    return classes


def _parse_variables(
    parser: Any, captures: list[tuple[Any, str]], source_code: str, path: Path
) -> list[dict[str, Any]]:
    """Parse Haskell-style variable declarations."""
    variables: list[dict[str, Any]] = []
    seen_vars: set[int] = set()

    for node, capture_name in captures:
        if capture_name != "variable":
            continue
        try:
            start_line = node.start_point[0] + 1
            ctx_name, ctx_type, _ = parser._get_parent_context(node)

            var_name = "unknown"
            var_type = "Unknown"
            var_decl = None
            for child in node.children:
                if child.type == "variable_declaration":
                    var_decl = child
                    break
            if var_decl is not None:
                for child in var_decl.children:
                    if child.type == "simple_identifier":
                        var_name = parser._get_node_text(child)
                    if child.type == "user_type":
                        var_type = parser._get_node_text(child)

            if var_type == "Unknown":
                for child in node.children:
                    if child.type == "call_expression":
                        for sub in child.children:
                            if sub.type == "simple_identifier":
                                var_type = parser._get_node_text(sub)
                                break
                        if var_type != "Unknown":
                            break

            if var_name == "unknown":
                continue
            start_byte = node.start_byte
            if start_byte in seen_vars:
                continue
            seen_vars.add(start_byte)
            variables.append(
                {
                    "name": var_name,
                    "type": var_type,
                    "line_number": start_line,
                    "path": str(path),
                    "lang": parser.language_name,
                    "context": ctx_name,
                    "class_context": (
                        ctx_name
                        if ctx_type and ("class" in ctx_type or "object" in ctx_type)
                        else None
                    ),
                }
            )
        except Exception:
            continue

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
            path = text.replace("import", "").strip().split(" as ")[0].strip()
            alias = text.split(" as ")[1].strip() if " as " in text else None
            imports.append(
                {
                    "name": path,
                    "full_import_name": path,
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
    """Parse Haskell call expressions."""
    calls: list[dict[str, Any]] = []
    seen_calls: set[tuple[str, int]] = set()
    var_map: dict[tuple[str, str | None], str] = {}
    for variable in variables or []:
        var_map[(variable["name"], variable["context"])] = variable["type"]

    for node, capture_name in captures:
        if capture_name != "call_node":
            continue
        try:
            start_line = node.start_point[0] + 1
            call_name = "unknown"
            base_obj = None

            children = node.children
            first_child = children[0] if children else None
            if first_child is None:
                continue
            if first_child.type == "simple_identifier":
                call_name = parser._get_node_text(first_child)
            elif first_child.type == "navigation_expression":
                nav_children = first_child.children
                if len(nav_children) >= 2:
                    operand = nav_children[0]
                    suffix = nav_children[-1]
                    if suffix.type == "navigation_suffix":
                        for child in suffix.children:
                            if child.type == "simple_identifier":
                                call_name = parser._get_node_text(child)
                                break
                    elif suffix.type == "simple_identifier":
                        call_name = parser._get_node_text(suffix)
                    base_obj = parser._get_node_text(operand)

            if call_name == "unknown":
                continue
            full_name = f"{base_obj}.{call_name}" if base_obj else call_name
            call_key = (full_name, start_line)
            if call_key in seen_calls:
                continue
            seen_calls.add(call_key)

            ctx_name, ctx_type, ctx_line = parser._get_parent_context(node)
            inferred_type = None
            if base_obj:
                inferred_type = var_map.get((base_obj, ctx_name))
                if not inferred_type:
                    inferred_type = var_map.get((base_obj, None))
                if not inferred_type:
                    for (var_name, _), var_type in var_map.items():
                        if var_name == base_obj:
                            inferred_type = var_type
                            break

            calls.append(
                {
                    "name": call_name,
                    "full_name": full_name,
                    "line_number": start_line,
                    "args": [],
                    "inferred_obj_type": inferred_type,
                    "context": [None, ctx_type, ctx_line],
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

            package_name = ""
            pkg_match = re.search(r"^\s*package\s+([\w\.]+)", content, re.MULTILINE)
            if pkg_match:
                package_name = pkg_match.group(1)

            matches = re.finditer(
                r"^\s*(class|object|interface|typealias)\s+(\w+)",
                content,
                re.MULTILINE,
            )
            for match in matches:
                name = match.group(2)
                imports_map.setdefault(name, []).append(str(path))
                if package_name:
                    imports_map.setdefault(f"{package_name}.{name}", []).append(
                        str(path)
                    )
        except Exception as exc:
            warning_logger(f"Tree-sitter pre-scan failed for {path}: {exc}")
    return imports_map
