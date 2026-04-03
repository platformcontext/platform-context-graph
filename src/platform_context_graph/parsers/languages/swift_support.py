"""Swift parser support helpers and query constants."""

from pathlib import Path
import re
from typing import Any

SWIFT_QUERIES = {
    "functions": """
        [
            (function_declaration
                name: (simple_identifier) @name
            ) @function_node
            (init_declaration) @init_node
        ]
    """,
    "classes": """
        [
            (class_declaration
                declaration_kind: "class"
                name: (type_identifier) @name
            ) @class
            (class_declaration
                declaration_kind: "struct"
                name: (type_identifier) @name
            ) @struct
            (class_declaration
                declaration_kind: "enum"
                name: (type_identifier) @name
            ) @enum
            (class_declaration
                declaration_kind: "protocol"
                name: (type_identifier) @name
            ) @protocol
            (class_declaration
                declaration_kind: "actor"
                name: (type_identifier) @name
            ) @class
        ]
    """,
    "imports": """
        (import_declaration) @import
    """,
    "calls": """
        (call_expression) @call_node
    """,
    "variables": """
        [
            (property_declaration
                name: (pattern
                    bound_identifier: (simple_identifier) @name
                )
            ) @variable
            (property_declaration
                name: (pattern) @pattern
            ) @variable
        ]
    """,
}


def get_parent_context(
    node: Any, get_node_text: Any
) -> tuple[str | None, str | None, int | None]:
    """Return the nearest enclosing Swift declaration for a node.

    Args:
        node: Tree-sitter node whose enclosing declaration is needed.
        get_node_text: Callable that decodes a node to source text.

    Returns:
        A tuple of declaration name, declaration type, and 1-based start line.
    """
    curr = node.parent
    while curr:
        if curr.type == "function_declaration":
            name_node = None
            for child in curr.children:
                if child.type == "simple_identifier":
                    name_node = child
                    break
            return (
                get_node_text(name_node) if name_node else None,
                curr.type,
                curr.start_point[0] + 1,
            )
        if curr.type in (
            "class_declaration",
            "struct_declaration",
            "enum_declaration",
            "protocol_declaration",
        ):
            for child in curr.children:
                if child.type == "type_identifier":
                    return (
                        get_node_text(child),
                        curr.type,
                        curr.start_point[0] + 1,
                    )
        if curr.type == "init_declaration":
            parent = curr.parent
            if parent and parent.type in ("class_body", "struct_body"):
                grandparent = parent.parent
                if grandparent:
                    for child in grandparent.children:
                        if child.type == "type_identifier":
                            return (
                                get_node_text(child),
                                grandparent.type,
                                grandparent.start_point[0] + 1,
                            )
            return ("init", curr.type, curr.start_point[0] + 1)
        curr = curr.parent
    return None, None, None


def extract_parameter_name(param_node: Any, get_node_text: Any) -> str | None:
    """Extract a Swift parameter name from a parameter node.

    Args:
        param_node: Tree-sitter parameter node.
        get_node_text: Callable that decodes a node to source text.

    Returns:
        The first parameter identifier found, if any.
    """
    for child in param_node.children:
        if child.type == "simple_identifier":
            return get_node_text(child)
    return None


def pre_scan_swift(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Build a type-to-file map for Swift source files.

    Args:
        files: Swift files to scan.
        parser_wrapper: Unused compatibility argument kept for the public API.

    Returns:
        Mapping of type names to file paths where they appear.
    """
    del parser_wrapper
    name_to_files: dict[str, list[str]] = {}
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()
        except OSError:
            continue

        matches = re.finditer(r"\b(class|struct|enum|protocol)\s+(\w+)", content)
        for match in matches:
            name = match.group(2)
            if name not in name_to_files:
                name_to_files[name] = []
            name_to_files[name].append(str(path))

    return name_to_files
