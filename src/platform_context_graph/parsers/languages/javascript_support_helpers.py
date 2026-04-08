"""Low-level helpers for the JavaScript parser support module."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

_GETTER_RE = re.compile(r"^\s*(?:static\s+)?get\b")
_SETTER_RE = re.compile(r"^\s*(?:static\s+)?set\b")
_STATIC_RE = re.compile(r"^\s*static\b")


def empty_result(path: Path, language_name: str, is_dependency: bool) -> dict[str, Any]:
    """Return the canonical empty parse payload for a JavaScript file."""
    return {
        "path": str(path),
        "functions": [],
        "classes": [],
        "variables": [],
        "imports": [],
        "function_calls": [],
        "framework_semantics": {"frameworks": []},
        "is_dependency": is_dependency,
        "lang": language_name,
    }


def node_text(node: Any) -> str:
    """Decode a tree-sitter node to UTF-8 text."""
    return node.text.decode("utf-8")


def first_line_before_body(text: str) -> str:
    """Return the declaration header before the first body brace."""
    header = text.split("{", 1)[0]
    if header.strip():
        return header
    lines = text.splitlines()
    return lines[0] if lines else text


def classify_method_kind(header: str) -> str | None:
    """Classify a JavaScript method header as getter, setter, or static."""
    if _GETTER_RE.search(header):
        return "getter"
    if _SETTER_RE.search(header):
        return "setter"
    if _STATIC_RE.search(header):
        return "static"
    return None


def get_parent_context(
    node: Any,
    get_node_text: Callable[[Any], str],
    types: tuple[str, ...] = (
        "function_declaration",
        "class_declaration",
        "function_expression",
        "method_definition",
        "arrow_function",
    ),
) -> tuple[str | None, str | None, int | None]:
    """Return the nearest enclosing JavaScript declaration for a node."""
    curr = node.parent
    while curr:
        if curr.type in types:
            name_node = curr.child_by_field_name("name")
            if not name_node and curr.type in ("function_expression", "arrow_function"):
                if curr.parent and curr.parent.type == "variable_declarator":
                    name_node = curr.parent.child_by_field_name("name")
                elif curr.parent and curr.parent.type == "assignment_expression":
                    name_node = curr.parent.child_by_field_name("left")
                elif curr.parent and curr.parent.type == "pair":
                    name_node = curr.parent.child_by_field_name("key")
            return (
                get_node_text(name_node) if name_node else None,
                curr.type,
                curr.start_point[0] + 1,
            )
        curr = curr.parent
    return None, None, None


def extract_parameters(
    params_node: Any, get_node_text: Callable[[Any], str]
) -> list[str]:
    """Extract JavaScript parameter names from a formal parameter list."""
    params: list[str] = []
    if params_node.type != "formal_parameters":
        return params
    for child in params_node.children:
        if child.type == "identifier":
            params.append(get_node_text(child))
        elif child.type == "assignment_pattern":
            left_child = child.child_by_field_name("left")
            if left_child and left_child.type == "identifier":
                params.append(get_node_text(left_child))
        elif child.type == "rest_pattern":
            argument = child.child_by_field_name("argument")
            if argument and argument.type == "identifier":
                params.append(f"...{get_node_text(argument)}")
    return params


def get_jsdoc_comment(
    func_node: Any, get_node_text: Callable[[Any], str]
) -> str | None:
    """Return a JSDoc comment immediately preceding a function node."""
    prev_sibling = func_node.prev_sibling
    while prev_sibling and prev_sibling.type in ("comment", "\n", " "):
        if prev_sibling.type == "comment":
            comment_text = get_node_text(prev_sibling)
            if comment_text.startswith("/**") and comment_text.endswith("*/"):
                return comment_text.strip()
        prev_sibling = prev_sibling.prev_sibling
    return None


def find_function_node_for_name(name_node: Any) -> Any | None:
    """Find the function node associated with a captured JavaScript name node."""
    current = name_node.parent
    while current:
        if current.type in (
            "function_declaration",
            "function",
            "arrow_function",
            "method_definition",
            "function_expression",
        ):
            return current
        if current.type in ("variable_declarator", "assignment_expression"):
            for child in current.children:
                if child.type in ("function", "arrow_function", "function_expression"):
                    return child
        current = current.parent
    return None


def find_function_node_for_params(params_node: Any) -> Any | None:
    """Find the function node associated with a captured parameter node."""
    current = params_node.parent
    while current:
        if current.type in (
            "function_declaration",
            "function",
            "arrow_function",
            "method_definition",
            "function_expression",
        ):
            return current
        current = current.parent
    return None
