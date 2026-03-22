"""Support helpers for the handwritten Java parser."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

JAVA_QUERIES = {
    "functions": """
        (method_declaration
            name: (identifier) @name
            parameters: (formal_parameters) @params
        ) @function_node

        (constructor_declaration
            name: (identifier) @name
            parameters: (formal_parameters) @params
        ) @function_node
    """,
    "classes": """
        [
            (class_declaration name: (identifier) @name)
            (interface_declaration name: (identifier) @name)
            (enum_declaration name: (identifier) @name)
            (annotation_type_declaration name: (identifier) @name)
        ] @class
    """,
    "imports": """
        (import_declaration) @import
    """,
    "calls": """
        (method_invocation
            name: (identifier) @name
        ) @call_node

        (object_creation_expression
            type: [
                (type_identifier)
                (scoped_type_identifier)
                (generic_type)
            ] @name
        ) @call_node
    """,
    "variables": """
        (local_variable_declaration
            type: (_) @type
            declarator: (variable_declarator
                name: (identifier) @name
            )
        ) @variable

        (field_declaration
            type: (_) @type
            declarator: (variable_declarator
                name: (identifier) @name
            )
        ) @variable
    """,
}


def _empty_result(path: Path, is_dependency: bool) -> dict[str, Any]:
    """Return the standard empty parse payload for Java files."""
    return {
        "path": str(path),
        "functions": [],
        "classes": [],
        "variables": [],
        "imports": [],
        "function_calls": [],
        "is_dependency": is_dependency,
        "lang": "java",
    }


def parse_java_file(
    parser: Any, path: Path, is_dependency: bool = False, index_source: bool = False
) -> dict[str, Any]:
    """Parse one Java file into the repository's normalized structure."""
    try:
        parser.index_source = index_source
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            source_code = handle.read()

        if not source_code.strip():
            warning_logger(f"Empty or whitespace-only file: {path}")
            return _empty_result(path, is_dependency)

        tree = parser.parser.parse(bytes(source_code, "utf8"))

        parsed_functions: list[dict[str, Any]] = []
        parsed_classes: list[dict[str, Any]] = []
        parsed_variables: list[dict[str, Any]] = []
        parsed_imports: list[dict[str, Any]] = []
        parsed_calls: list[dict[str, Any]] = []

        for capture_name, query in JAVA_QUERIES.items():
            results = execute_query(parser.language, query, tree.root_node)
            if capture_name == "functions":
                parsed_functions = _parse_functions(parser, results, source_code, path)
            elif capture_name == "classes":
                parsed_classes = _parse_classes(parser, results, source_code, path)
            elif capture_name == "imports":
                parsed_imports = _parse_imports(parser, results, source_code)
            elif capture_name == "calls":
                parsed_calls = _parse_calls(parser, results, source_code)
            elif capture_name == "variables":
                parsed_variables = _parse_variables(parser, results, source_code, path)

        return {
            "path": str(path),
            "functions": parsed_functions,
            "classes": parsed_classes,
            "variables": parsed_variables,
            "imports": parsed_imports,
            "function_calls": parsed_calls,
            "is_dependency": is_dependency,
            "lang": "java",
        }
    except Exception as exc:
        error_logger(f"Error parsing Java file {path}: {exc}")
        return _empty_result(path, is_dependency)


def _get_parent_context(
    parser: Any, node: Any
) -> tuple[str | None, str | None, int | None]:
    """Find the nearest enclosing Java declaration for a node."""
    curr = node.parent
    while curr:
        if curr.type in ("method_declaration", "constructor_declaration"):
            name_node = curr.child_by_field_name("name")
            return (
                _get_node_text(name_node) if name_node else None,
                curr.type,
                curr.start_point[0] + 1,
            )
        if curr.type in (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "annotation_type_declaration",
        ):
            name_node = curr.child_by_field_name("name")
            return (
                _get_node_text(name_node) if name_node else None,
                curr.type,
                curr.start_point[0] + 1,
            )
        curr = curr.parent
    return None, None, None


def _get_node_text(node: Any) -> str:
    """Return decoded source text for a tree-sitter node."""
    if not node:
        return ""
    return node.text.decode("utf-8")


def _parse_functions(
    parser: Any, captures: list, source_code: str, path: Path
) -> list[dict[str, Any]]:
    """Parse Java function and constructor declarations."""
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
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue

            func_name = _get_node_text(name_node)
            params_node = node.child_by_field_name("parameters")
            parameters = (
                _extract_parameter_names(parser, _get_node_text(params_node))
                if params_node
                else []
            )
            source_text = _get_node_text(node)
            context_name, context_type, _ = _get_parent_context(parser, node)

            func_data = {
                "name": func_name,
                "parameters": parameters,
                "line_number": start_line,
                "end_line": end_line,
                "path": str(path),
                "lang": "java",
                "context": context_name,
                "class_context": (
                    context_name if context_type and "class" in context_type else None
                ),
            }
            if parser.index_source:
                func_data["source"] = source_text
            functions.append(func_data)
        except Exception as exc:
            error_logger(f"Error parsing function in {path}: {exc}")
    return functions


def _parse_classes(
    parser: Any, captures: list, source_code: str, path: Path
) -> list[dict[str, Any]]:
    """Parse Java class, interface, enum, and annotation declarations."""
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
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue

            class_name = _get_node_text(name_node)
            source_text = _get_node_text(node)
            bases: list[str] = []

            superclass_node = node.child_by_field_name("superclass")
            if superclass_node:
                bases.append(_get_node_text(superclass_node))

            interfaces_node = node.child_by_field_name("interfaces")
            if not interfaces_node:
                interfaces_node = next(
                    (
                        child
                        for child in node.children
                        if child.type == "super_interfaces"
                    ),
                    None,
                )

            if interfaces_node:
                type_list = interfaces_node.child_by_field_name("list")
                if not type_list:
                    type_list = next(
                        (
                            child
                            for child in interfaces_node.children
                            if child.type == "type_list"
                        ),
                        None,
                    )

                if type_list:
                    iterable = type_list.children
                else:
                    iterable = interfaces_node.children

                for child in iterable:
                    if child.type in (
                        "type_identifier",
                        "generic_type",
                        "scoped_type_identifier",
                    ):
                        bases.append(_get_node_text(child))

            class_data = {
                "name": class_name,
                "line_number": start_line,
                "end_line": end_line,
                "bases": bases,
                "path": str(path),
                "lang": "java",
            }
            if parser.index_source:
                class_data["source"] = source_text
            classes.append(class_data)
        except Exception as exc:
            error_logger(f"Error parsing class in {path}: {exc}")

    return classes


def _parse_variables(
    parser: Any, captures: list, source_code: str, path: Path
) -> list[dict[str, Any]]:
    """Parse Java variable declarations."""
    variables: list[dict[str, Any]] = []
    seen_vars: set[int] = set()

    for node, capture_name in captures:
        if capture_name != "name" or node.parent.type != "variable_declarator":
            continue

        var_name = _get_node_text(node)
        start_line = node.start_point[0] + 1
        declaration = node.parent.parent
        type_node = declaration.child_by_field_name("type")
        var_type = _get_node_text(type_node) if type_node else "Unknown"

        start_byte = node.start_byte
        if start_byte in seen_vars:
            continue
        seen_vars.add(start_byte)

        ctx_name, ctx_type, _ = _get_parent_context(parser, node)
        variables.append(
            {
                "name": var_name,
                "type": var_type,
                "line_number": start_line,
                "path": str(path),
                "lang": "java",
                "context": ctx_name,
                "class_context": (
                    ctx_name if ctx_type and "class" in ctx_type else None
                ),
            }
        )

    return variables


def _parse_imports(
    parser: Any, captures: list, source_code: str
) -> list[dict[str, Any]]:
    """Parse Java import declarations."""
    imports: list[dict[str, Any]] = []

    for node, capture_name in captures:
        if capture_name != "import":
            continue
        try:
            import_text = _get_node_text(node)
            import_match = re.search(r"import\s+(?:static\s+)?([^;]+)", import_text)
            if not import_match:
                continue
            import_path = import_match.group(1).strip()
            imports.append(
                {
                    "name": import_path,
                    "full_import_name": import_path,
                    "line_number": node.start_point[0] + 1,
                    "alias": None,
                    "context": (None, None),
                    "lang": "java",
                    "is_dependency": False,
                }
            )
        except Exception as exc:
            error_logger(f"Error parsing import: {exc}")

    return imports


def _parse_calls(parser: Any, captures: list, source_code: str) -> list[dict[str, Any]]:
    """Parse Java method invocation and object creation calls."""
    calls: list[dict[str, Any]] = []
    seen_calls: set[str] = set()

    for node, capture_name in captures:
        if capture_name != "name":
            continue

        try:
            call_name = _get_node_text(node)
            line_number = node.start_point[0] + 1
            call_node = node.parent
            while call_node and call_node.type not in (
                "method_invocation",
                "object_creation_expression",
            ):
                call_node = call_node.parent
            if not call_node:
                call_node = node

            call_key = f"{call_name}_{line_number}"
            if call_key in seen_calls:
                continue
            seen_calls.add(call_key)

            args: list[str] = []
            args_node = next(
                (
                    child
                    for child in call_node.children
                    if child.type == "argument_list"
                ),
                None,
            )
            if args_node:
                for arg in args_node.children:
                    if arg.type not in ("(", ")", ","):
                        args.append(_get_node_text(arg))

            full_name = call_name
            if call_node.type == "method_invocation":
                obj_node = call_node.child_by_field_name("object")
                if obj_node:
                    full_name = f"{_get_node_text(obj_node)}.{call_name}"
            elif call_node.type == "object_creation_expression":
                type_node = call_node.child_by_field_name("type")
                if type_node:
                    full_name = _get_node_text(type_node)

            ctx_name, ctx_type, ctx_line = _get_parent_context(parser, node)
            call_data = {
                "name": call_name,
                "full_name": full_name,
                "line_number": line_number,
                "args": args,
                "inferred_obj_type": None,
                "context": (ctx_name, ctx_type, ctx_line),
                "class_context": (
                    (ctx_name, ctx_line)
                    if ctx_type and "class" in ctx_type
                    else (None, None)
                ),
                "lang": "java",
                "is_dependency": False,
            }
            calls.append(call_data)
        except Exception as exc:
            error_logger(f"Error parsing call: {exc}")

    return calls


def _extract_parameter_names(parser: Any, params_text: str) -> list[str]:
    """Extract Java parameter names from a raw formal-parameter string."""
    del parser
    params: list[str] = []
    if not params_text or params_text.strip() == "()":
        return params

    params_content = params_text.strip("()")
    if not params_content:
        return params

    for param in params_content.split(","):
        param = param.strip()
        if not param:
            continue
        parts = param.split()
        if len(parts) >= 2:
            params.append(parts[-1])

    return params
