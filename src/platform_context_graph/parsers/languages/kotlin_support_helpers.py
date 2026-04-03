"""Low-level helpers for the Kotlin parser support module."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import error_logger, warning_logger

KOTLIN_QUERIES = {
    "functions": """
        (function_declaration
            (simple_identifier) @name
            (function_value_parameters) @params
        ) @function_node
    """,
    "classes": """
        [
            (class_declaration (type_identifier) @name)
            (object_declaration (type_identifier) @name)
            (companion_object (type_identifier)? @name)
        ] @class
    """,
    "imports": """
        (import_header) @import
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


def empty_result(path: Path, language_name: str, is_dependency: bool) -> dict[str, Any]:
    """Return the canonical empty parse payload for a Kotlin file."""
    return {
        "path": str(path),
        "functions": [],
        "classes": [],
        "variables": [],
        "imports": [],
        "function_calls": [],
        "is_dependency": is_dependency,
        "lang": language_name,
    }


def node_text(node: Any) -> str:
    """Decode a tree-sitter node to UTF-8 text."""
    return node.text.decode("utf-8")


def get_parent_context(node: Any) -> tuple[str | None, str | None, int | None]:
    """Return the nearest enclosing Kotlin declaration for a node."""
    curr = node.parent
    while curr:
        if curr.type == "function_declaration":
            for child in curr.children:
                if child.type == "simple_identifier":
                    return node_text(child), curr.type, curr.start_point[0] + 1
        if curr.type in ("class_declaration", "object_declaration"):
            for child in curr.children:
                if child.type in ("simple_identifier", "type_identifier"):
                    return node_text(child), curr.type, curr.start_point[0] + 1
        if curr.type == "secondary_constructor":
            return "constructor", curr.type, curr.start_point[0] + 1
        if curr.type == "companion_object":
            name = "Companion"
            for child in curr.children:
                if child.type in ("simple_identifier", "type_identifier"):
                    name = node_text(child)
                    break
            return name, curr.type, curr.start_point[0] + 1
        if curr.type == "object_literal":
            return "AnonymousObject", curr.type, curr.start_point[0] + 1
        curr = curr.parent
    return None, None, None


def extract_parameter_names(params_text: str) -> list[str]:
    """Extract parameter names from a Kotlin parameter list string."""
    params: list[str] = []
    if not params_text:
        return params
    clean = params_text.strip()
    if clean.startswith("(") and clean.endswith(")"):
        clean = clean[1:-1]
    if not clean.strip():
        return params

    current_param: list[str] = []
    depth_angle = depth_round = depth_square = depth_curly = 0
    raw_params: list[str] = []
    for char in clean:
        if char == "<":
            depth_angle += 1
        elif char == ">":
            depth_angle -= 1
        elif char == "(":
            depth_round += 1
        elif char == ")":
            depth_round -= 1
        elif char == "[":
            depth_square += 1
        elif char == "]":
            depth_square -= 1
        elif char == "{":
            depth_curly += 1
        elif char == "}":
            depth_curly -= 1
        if char == "," and not any(
            (depth_angle, depth_round, depth_square, depth_curly)
        ):
            raw_params.append("".join(current_param).strip())
            current_param = []
        else:
            current_param.append(char)
    if current_param:
        raw_params.append("".join(current_param).strip())

    for param in raw_params:
        if not param:
            continue
        lhs = param.split(":", 1)[0].strip() if ":" in param else param.strip()
        if not lhs:
            continue
        tokens = lhs.split()
        if tokens:
            params.append(tokens[-1])
    return params
