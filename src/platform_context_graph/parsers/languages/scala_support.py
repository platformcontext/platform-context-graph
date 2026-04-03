"""Support constants and helper functions for the Scala parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import re

from platform_context_graph.utils.debug_log import error_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

SCALA_QUERIES = {
    "functions": """
        (function_definition
            name: (identifier) @name
            parameters: (parameters) @params
        ) @function_node
    """,
    "classes": """
        [
            (class_definition name: (identifier) @name)
            (object_definition name: (identifier) @name)
            (trait_definition name: (identifier) @name)
        ] @class
    """,
    "imports": """
        (import_declaration) @import
    """,
    "calls": """
        (call_expression) @call_node
        (generic_function
             function: (identifier) @name
        ) @call_node
    """,
    "variables": """
        (val_definition
            pattern: (identifier) @name
        ) @variable

        (var_definition
            pattern: (identifier) @name
        ) @variable
    """,
}


def _parse_functions(
    parser: Any, captures: list[tuple[Any, str]], source_code: str, path: Path
) -> list[dict[str, Any]]:
    """Parse Scala function declarations."""
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
            if name_node is None:
                continue

            params_node = node.child_by_field_name("parameters")
            parameters: list[str] = []
            if params_node is not None:
                parameters = _extract_parameter_names(
                    parser._get_node_text(params_node)
                )

            context_name, context_type, _ = parser._get_parent_context(node)
            function_data = {
                "name": parser._get_node_text(name_node),
                "parameters": parameters,
                "args": parameters,
                "line_number": start_line,
                "end_line": end_line,
                "path": str(path),
                "lang": parser.language_name,
                "context": context_name,
                "class_context": (
                    context_name
                    if context_type
                    and any(
                        token in str(context_type)
                        for token in ("class", "object", "trait")
                    )
                    else None
                ),
            }
            if parser.index_source:
                function_data["source"] = parser._get_node_text(node)
            functions.append(function_data)
        except Exception as exc:
            error_logger(f"Error parsing function in {path}: {exc}")

    return functions


def _parse_classes(
    parser: Any, captures: list[tuple[Any, str]], source_code: str, path: Path
) -> list[dict[str, Any]]:
    """Parse Scala class, object, and trait declarations."""
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
            if name_node is None:
                continue

            bases: list[str] = []
            extends_clause = next(
                (child for child in node.children if child.type == "extends_clause"),
                None,
            )
            if extends_clause is not None:
                for child in extends_clause.children:
                    if child.type in ("type_identifier", "user_type"):
                        bases.append(parser._get_node_text(child))

            class_data = {
                "name": parser._get_node_text(name_node),
                "line_number": start_line,
                "end_line": end_line,
                "bases": bases,
                "path": str(path),
                "lang": parser.language_name,
                "type": node.type.replace("_definition", ""),
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
    """Parse Scala value and variable declarations."""
    variables: list[dict[str, Any]] = []
    seen_vars: set[int] = set()

    for node, capture_name in captures:
        if capture_name != "name":
            continue
        try:
            parent = node.parent
            if parent is None or parent.type not in (
                "val_definition",
                "var_definition",
            ):
                continue
            start_byte = node.start_byte
            if start_byte in seen_vars:
                continue
            seen_vars.add(start_byte)

            var_name = parser._get_node_text(node)
            start_line = node.start_point[0] + 1
            ctx_name, ctx_type, _ = parser._get_parent_context(node)
            var_type = "Unknown"

            type_node = parent.child_by_field_name("type")
            if type_node is not None:
                var_type = parser._get_node_text(type_node)
            else:
                val_node = parent.child_by_field_name("value")
                if val_node is not None:
                    if val_node.type in ("instance_expression", "new_expression"):
                        for child in val_node.children:
                            if child.type in (
                                "type_identifier",
                                "simple_type",
                                "user_type",
                                "generic_type",
                            ):
                                var_type = parser._get_node_text(child)
                                break
                    elif val_node.type == "call_expression":
                        func = val_node.child_by_field_name("function")
                        if func is not None:
                            var_type = parser._get_node_text(func)

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
                        if ctx_type
                        and ("class" in str(ctx_type) or "object" in str(ctx_type))
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
    """Parse Scala import declarations."""
    imports: list[dict[str, Any]] = []

    for node, capture_name in captures:
        if capture_name != "import":
            continue
        try:
            import_text = parser._get_node_text(node)
            clean_text = import_text.replace("import ", "").strip()
            if not clean_text:
                continue
            imports.append(
                {
                    "name": clean_text,
                    "full_import_name": clean_text,
                    "line_number": node.start_point[0] + 1,
                    "alias": None,
                    "context": (None, None),
                    "lang": parser.language_name,
                    "is_dependency": False,
                }
            )
        except Exception as exc:
            error_logger(f"Error parsing import in Scala source: {exc}")

    return imports


def _parse_calls(
    parser: Any,
    captures: list[tuple[Any, str]],
    source_code: str,
    path: Path,
    variables: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Parse Scala call expressions."""
    calls: list[dict[str, Any]] = []
    seen_calls: set[tuple[str, int]] = set()
    variables = variables or []

    for node, capture_name in captures:
        if capture_name != "call_node":
            continue
        try:
            start_line = node.start_point[0] + 1
            call_name = "unknown"
            full_name = "unknown"

            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node is not None:
                    if func_node.type == "field_expression":
                        field = func_node.child_by_field_name("field")
                        call_name = parser._get_node_text(field) if field else "unknown"
                        full_name = parser._get_node_text(func_node)
                    elif func_node.type == "identifier":
                        call_name = parser._get_node_text(func_node)
                        full_name = call_name
                    elif func_node.type == "generic_function":
                        inner = func_node.child_by_field_name("function")
                        if inner is not None:
                            full_name = parser._get_node_text(inner)
                            call_name = full_name

            if call_name == "unknown":
                continue

            call_key = (call_name, start_line)
            if call_key in seen_calls:
                continue
            seen_calls.add(call_key)

            ctx_name, ctx_type, ctx_line = parser._get_parent_context(node)
            inferred_type = None
            if "." in full_name:
                base_obj = full_name.split(".")[0]
                candidate = next((v for v in variables if v["name"] == base_obj), None)
                if candidate is not None:
                    inferred_type = candidate["type"]

            calls.append(
                {
                    "name": call_name,
                    "full_name": full_name,
                    "line_number": start_line,
                    "args": [],
                    "inferred_obj_type": inferred_type,
                    "context": (ctx_name, ctx_type, ctx_line),
                    "class_context": (
                        (ctx_name, ctx_line)
                        if ctx_type
                        and ("class" in str(ctx_type) or "object" in str(ctx_type))
                        else (None, None)
                    ),
                    "lang": parser.language_name,
                    "is_dependency": False,
                }
            )
        except Exception as exc:
            error_logger(f"Error parsing call in Scala source: {exc}")

    return calls


def _extract_parameter_names(params_text: str) -> list[str]:
    """Extract Scala parameter names from a parameter list string."""
    params: list[str] = []
    if not params_text:
        return params
    clean = params_text.strip("()")
    if not clean:
        return params
    for part in clean.split(","):
        if ":" in part:
            name = part.split(":")[0].strip()
            tokens = name.split()
            if tokens:
                params.append(tokens[-1])
        else:
            params.append(part.strip())
    return params


def pre_scan_scala(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Build a name-to-file map for Scala declarations."""
    name_to_files: dict[str, list[str]] = {}
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()
            package_name = ""
            pkg_match = re.search(r"^\s*package\s+([\w\.]+)", content, re.MULTILINE)
            if pkg_match:
                package_name = pkg_match.group(1)
            class_matches = re.finditer(r"\b(class|object|trait)\s+(\w+)", content)
            for match in class_matches:
                name = match.group(2)
                name_to_files.setdefault(name, []).append(str(path))
                if package_name:
                    name_to_files.setdefault(f"{package_name}.{name}", []).append(
                        str(path)
                    )
        except Exception as exc:
            error_logger(f"Error pre-scanning Scala file {path}: {exc}")
    return name_to_files
