"""Support constants and helper functions for the PHP parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import re

from platform_context_graph.utils.tree_sitter_manager import execute_query

PHP_QUERIES = {
    "functions": """
        (function_definition
            name: (name) @name
            parameters: (formal_parameters) @params
        ) @function_node

        (method_declaration
            name: (name) @name
            parameters: (formal_parameters) @params
        ) @function_node
    """,
    "classes": """
        (class_declaration
            name: (name) @name
        ) @class

        (interface_declaration
            name: (name) @name
        ) @interface

        (trait_declaration
            name: (name) @name
        ) @trait
    """,
    "imports": """
        (use_declaration) @import
    """,
    "calls": """
        (function_call_expression
            function: [
                (qualified_name) @name
                (name) @name
            ]
        ) @call_node

        (member_call_expression
            name: (name) @name
        ) @call_node

        (scoped_call_expression
            name: (name) @name
        ) @call_node

        (object_creation_expression) @call_node
    """,
    "variables": """
        (variable_name) @variable
    """,
}


def _parse_functions(
    parser: Any, captures: list[tuple[Any, str]], source_code: str, path: Path
) -> list[dict[str, Any]]:
    """Parse PHP function and method declarations."""
    functions: list[dict[str, Any]] = []
    seen_nodes: set[tuple[int, int, str]] = set()

    for node, capture_name in captures:
        if capture_name != "function_node":
            continue
        node_id = (node.start_byte, node.end_byte, node.type)
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)

        try:
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue

            params_node = node.child_by_field_name("parameters")
            parameters: list[str] = []
            if params_node is not None:
                for child in params_node.children:
                    if (
                        "variable_name" in child.type
                        or "simple_parameter" in child.type
                    ):
                        var_node = (
                            child
                            if "variable_name" in child.type
                            else child.child_by_field_name("name")
                        )
                        if var_node is not None:
                            parameters.append(parser._get_node_text(var_node))

            context_name, context_type, _ = parser._get_parent_context(node)
            function_data = {
                "name": parser._get_node_text(name_node),
                "parameters": parameters,
                "line_number": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "path": str(path),
                "lang": parser.language_name,
                "context": context_name,
                "context_type": context_type,
                "class_context": (
                    context_name
                    if context_type
                    and (
                        "class" in context_type
                        or "interface" in context_type
                        or "trait" in context_type
                    )
                    else None
                ),
            }
            if parser.index_source:
                function_data["source"] = parser._get_node_text(node)
            functions.append(function_data)
        except Exception:
            continue

    return functions


def _parse_types(
    parser: Any, captures: list[tuple[Any, str]], source_code: str, path: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse PHP classes, interfaces, and traits."""
    classes: list[dict[str, Any]] = []
    interfaces: list[dict[str, Any]] = []
    traits: list[dict[str, Any]] = []
    seen_nodes: set[tuple[int, int, str]] = set()

    for node, capture_name in captures:
        if capture_name not in ("class", "interface", "trait"):
            continue
        node_id = (node.start_byte, node.end_byte, node.type)
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)

        try:
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue

            bases: list[str] = []
            base_clause_node = node.child_by_field_name("base_clause")
            interfaces_clause_node = node.child_by_field_name("interfaces_clause")
            if base_clause_node is not None:
                for child in base_clause_node.children:
                    if child.type in ("name", "qualified_name"):
                        bases.append(parser._get_node_text(child))
            if interfaces_clause_node is not None:
                for child in interfaces_clause_node.children:
                    if child.type in ("name", "qualified_name"):
                        bases.append(parser._get_node_text(child))

            type_data = {
                "name": parser._get_node_text(name_node),
                "line_number": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "bases": bases,
                "path": str(path),
                "lang": parser.language_name,
            }
            if parser.index_source:
                type_data["source"] = parser._get_node_text(node)

            if capture_name == "class":
                classes.append(type_data)
            elif capture_name == "interface":
                interfaces.append(type_data)
            else:
                traits.append(type_data)
        except Exception:
            continue

    return classes, interfaces, traits


def _parse_variables(
    parser: Any, captures: list[tuple[Any, str]], source_code: str, path: Path
) -> list[dict[str, Any]]:
    """Parse PHP variables and property declarations."""
    variables: list[dict[str, Any]] = []
    seen_vars: set[int] = set()

    for node, capture_name in captures:
        if capture_name != "variable":
            continue
        try:
            var_name = parser._get_node_text(node)
            start_line = node.start_point[0] + 1
            start_byte = node.start_byte
            if start_byte in seen_vars:
                continue
            seen_vars.add(start_byte)

            ctx_name, ctx_type, _ = parser._get_parent_context(node)
            inferred_type = "mixed"
            parent = node.parent
            if parent is not None and parent.type == "assignment_expression":
                left = parent.child_by_field_name("left")
                right = parent.child_by_field_name("right")
                if (
                    left == node
                    and right is not None
                    and right.type == "object_creation_expression"
                ):
                    for child in right.children:
                        if child.type in ("name", "qualified_name"):
                            inferred_type = parser._get_node_text(child)
                            break

            variables.append(
                {
                    "name": var_name,
                    "type": inferred_type,
                    "line_number": start_line,
                    "path": str(path),
                    "lang": parser.language_name,
                    "context": ctx_name,
                    "class_context": (
                        ctx_name
                        if ctx_type
                        and (
                            "class" in ctx_type
                            or "interface" in ctx_type
                            or "trait" in ctx_type
                        )
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
    """Parse PHP import declarations."""
    imports: list[dict[str, Any]] = []

    for node, capture_name in captures:
        if capture_name != "import":
            continue
        try:
            import_text = parser._get_node_text(node)
            import_match = re.search(r"use\s+([\w\\]+)(?:\s+as\s+(\w+))?", import_text)
            if not import_match:
                continue
            import_path = import_match.group(1).strip()
            alias = import_match.group(2).strip() if import_match.group(2) else None
            imports.append(
                {
                    "name": import_path,
                    "full_import_name": import_text,
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
    parser: Any, captures: list[tuple[Any, str]], source_code: str
) -> list[dict[str, Any]]:
    """Parse PHP function, method, and constructor calls."""
    calls: list[dict[str, Any]] = []
    seen_calls: set[tuple[str, int]] = set()

    for node, capture_name in captures:
        if capture_name == "name":
            try:
                call_name = parser._get_node_text(node)
                line_number = node.start_point[0] + 1
                call_node = node.parent
                while call_node and call_node.type not in (
                    "function_call_expression",
                    "member_call_expression",
                    "scoped_call_expression",
                ):
                    call_node = call_node.parent
                if call_node is None:
                    continue

                call_key = (call_name, line_number)
                if call_key in seen_calls:
                    continue
                seen_calls.add(call_key)

                args: list[str] = []
                args_node = call_node.child_by_field_name("arguments")
                if args_node is not None:
                    for arg in args_node.children:
                        if arg.type not in ("(", ")", ","):
                            args.append(parser._get_node_text(arg))

                full_name = call_name
                if call_node.type == "member_call_expression":
                    obj_node = call_node.child_by_field_name("object")
                    if obj_node is not None:
                        full_name = f"{parser._get_node_text(obj_node)}.{call_name}"
                elif call_node.type == "scoped_call_expression":
                    scope_node = call_node.child_by_field_name("scope")
                    if scope_node is not None:
                        full_name = f"{parser._get_node_text(scope_node)}.{call_name}"

                ctx_name, ctx_type, ctx_line = parser._get_parent_context(node)
                calls.append(
                    {
                        "name": call_name,
                        "full_name": full_name,
                        "line_number": line_number,
                        "args": args,
                        "inferred_obj_type": None,
                        "context": (ctx_name, ctx_type, ctx_line),
                        "class_context": (
                            (ctx_name, ctx_line)
                            if ctx_type
                            and (
                                "class" in ctx_type
                                or "interface" in ctx_type
                                or "trait" in ctx_type
                            )
                            else (None, None)
                        ),
                        "lang": parser.language_name,
                        "is_dependency": False,
                    }
                )
            except Exception:
                continue
        elif capture_name == "call_node" and node.type == "object_creation_expression":
            try:
                line_number = node.start_point[0] + 1
                class_name = "Unknown"
                for child in node.children:
                    if child.type in ("name", "qualified_name", "variable_name"):
                        class_name = parser._get_node_text(child)
                        break

                call_key = (f"new {class_name}", line_number)
                if call_key in seen_calls:
                    continue
                seen_calls.add(call_key)

                args: list[str] = []
                args_node = node.child_by_field_name("arguments")
                if args_node is not None:
                    for arg in args_node.children:
                        if arg.type not in ("(", ")", ","):
                            args.append(parser._get_node_text(arg))

                ctx_name, ctx_type, ctx_line = parser._get_parent_context(node)
                calls.append(
                    {
                        "name": class_name,
                        "full_name": class_name,
                        "line_number": line_number,
                        "args": args,
                        "inferred_obj_type": None,
                        "context": (ctx_name, ctx_type, ctx_line),
                        "class_context": (
                            (ctx_name, ctx_line)
                            if ctx_type
                            and (
                                "class" in ctx_type
                                or "interface" in ctx_type
                                or "trait" in ctx_type
                            )
                            else (None, None)
                        ),
                        "lang": parser.language_name,
                        "is_dependency": False,
                    }
                )
            except Exception:
                continue

    return calls


def pre_scan_php(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Return an empty pre-scan map for PHP source files."""
    return {}
