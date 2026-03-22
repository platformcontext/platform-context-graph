"""Support helpers for the handwritten Kotlin parser."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query
from .kotlin_support_helpers import (
    KOTLIN_QUERIES,
    empty_result as _empty_result,
    extract_parameter_names as _extract_parameter_names,
    get_parent_context as _get_parent_context,
    node_text as _node_text,
)


def _parse_functions(
    captures: list, source_code: str, path: Path, language_name: str, index_source: bool
) -> list[dict[str, Any]]:
    """Parse Kotlin function declarations from query captures."""
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
            name_node = next(
                (child for child in node.children if child.type == "simple_identifier"),
                None,
            )
            if not name_node:
                continue
            params_node = next(
                (
                    child
                    for child in node.children
                    if child.type == "function_value_parameters"
                ),
                None,
            )
            parameters = (
                _extract_parameter_names(_node_text(params_node)) if params_node else []
            )
            context_name, context_type, _ = _get_parent_context(node)
            func_data = {
                "name": _node_text(name_node),
                "args": parameters,
                "line_number": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "path": str(path),
                "lang": language_name,
                "context": context_name,
                "class_context": (
                    context_name
                    if context_type
                    and ("class" in context_type or "object" in context_type)
                    else None
                ),
            }
            if index_source:
                func_data["source"] = _node_text(node)
            functions.append(func_data)
        except Exception as exc:
            error_logger(f"Error parsing function in {path}: {exc}")
    return functions


def _parse_classes(
    captures: list, source_code: str, path: Path, language_name: str, index_source: bool
) -> list[dict[str, Any]]:
    """Parse Kotlin class-like declarations from query captures."""
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
            class_name = "Companion" if node.type == "companion_object" else "Anonymous"
            for child in node.children:
                if child.type in ("type_identifier", "simple_identifier"):
                    class_name = _node_text(child)
                    break
            bases: list[str] = []
            for child in node.children:
                if child.type != "delegation_specifier":
                    continue
                for specifier in child.children:
                    if specifier.type == "constructor_invocation":
                        for sub in specifier.children:
                            if sub.type == "user_type":
                                bases.append(_node_text(sub))
                                break
                    elif specifier.type == "user_type":
                        bases.append(_node_text(specifier))
            class_data = {
                "name": class_name,
                "line_number": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "bases": bases,
                "path": str(path),
                "lang": language_name,
            }
            if index_source:
                class_data["source"] = _node_text(node)
            classes.append(class_data)
        except Exception as exc:
            error_logger(f"Error parsing class in {path}: {exc}")
    return classes


def _parse_variables(
    captures: list, source_code: str, path: Path, language_name: str
) -> list[dict[str, Any]]:
    """Parse Kotlin variable declarations from query captures."""
    variables: list[dict[str, Any]] = []
    for node, capture_name in captures:
        if capture_name != "variable":
            continue
        try:
            start_line = node.start_point[0] + 1
            ctx_name, ctx_type, _ = _get_parent_context(node)
            var_name = "unknown"
            var_type = "Unknown"
            var_decl = next(
                (
                    child
                    for child in node.children
                    if child.type == "variable_declaration"
                ),
                None,
            )
            if var_decl:
                for child in var_decl.children:
                    if child.type == "simple_identifier":
                        var_name = _node_text(child)
                    elif child.type == "user_type":
                        var_type = _node_text(child)
            if var_type == "Unknown":
                for child in node.children:
                    if child.type == "call_expression":
                        for sub in child.children:
                            if sub.type == "simple_identifier":
                                var_type = _node_text(sub)
                                break
                        if var_type != "Unknown":
                            break
            if var_name != "unknown":
                variables.append(
                    {
                        "name": var_name,
                        "type": var_type,
                        "line_number": start_line,
                        "path": str(path),
                        "lang": language_name,
                        "context": ctx_name,
                        "class_context": (
                            ctx_name
                            if ctx_type
                            and ("class" in ctx_type or "object" in ctx_type)
                            else None
                        ),
                    }
                )
        except Exception:
            continue
    return variables


def _parse_imports(
    captures: list, source_code: str, language_name: str
) -> list[dict[str, Any]]:
    """Parse Kotlin import headers from query captures."""
    imports: list[dict[str, Any]] = []
    for node, capture_name in captures:
        if capture_name != "import":
            continue
        try:
            text = _node_text(node)
            path = text.replace("import ", "").strip().split(" as ")[0].strip()
            alias = text.split(" as ")[1].strip() if " as " in text else None
            imports.append(
                {
                    "name": path,
                    "full_import_name": path,
                    "line_number": node.start_point[0] + 1,
                    "alias": alias,
                    "context": (None, None),
                    "lang": language_name,
                    "is_dependency": False,
                }
            )
        except Exception:
            continue
    return imports


def _parse_calls(
    captures: list,
    source_code: str,
    path: Path,
    language_name: str,
    variables: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Parse Kotlin call expressions from query captures."""
    calls: list[dict[str, Any]] = []
    seen_calls: set[tuple[int, int, str]] = set()
    var_map: dict[tuple[str, str | None], str] = {}
    for variable in variables or []:
        var_map[(variable["name"], variable["context"])] = variable["type"]
    for node, capture_name in captures:
        if capture_name != "call_node":
            continue
        try:
            node_id = (node.start_byte, node.end_byte, node.type)
            if node_id in seen_calls:
                continue
            seen_calls.add(node_id)
            start_line = node.start_point[0] + 1
            call_name = "unknown"
            base_obj = None
            first_child = node.children[0] if node.children else None
            if first_child and first_child.type == "simple_identifier":
                call_name = _node_text(first_child)
            elif first_child and first_child.type == "navigation_expression":
                nav_children = first_child.children
                if len(nav_children) >= 2:
                    operand = nav_children[0]
                    suffix = nav_children[-1]
                    if suffix.type == "navigation_suffix":
                        for child in suffix.children:
                            if child.type == "simple_identifier":
                                call_name = _node_text(child)
                                break
                    elif suffix.type == "simple_identifier":
                        call_name = _node_text(suffix)
                    base_obj = _node_text(operand)
            if call_name == "unknown":
                continue
            full_name = f"{base_obj}.{call_name}" if base_obj else call_name
            ctx_name, ctx_type, ctx_line = _get_parent_context(node)
            inferred_type = None
            if base_obj:
                inferred_type = var_map.get((base_obj, ctx_name)) or var_map.get(
                    (base_obj, None)
                )
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
                    "lang": language_name,
                    "is_dependency": False,
                }
            )
        except Exception:
            continue
    return calls


class KotlinTreeSitterParser:
    """Parse Kotlin source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Store the generic parser wrapper used for parsing."""
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "kotlin"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser

    def parse(
        self,
        path: Path,
        is_dependency: bool = False,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Parse a Kotlin file into the standard graph-friendly structure."""
        return parse_kotlin_file(
            self,
            path,
            is_dependency=is_dependency,
            index_source=index_source,
        )


def parse_kotlin_file(
    parser_wrapper: Any,
    path: Path,
    *,
    is_dependency: bool = False,
    index_source: bool = False,
) -> dict[str, Any]:
    """Parse one Kotlin file into the repository graph schema."""
    try:
        parser_wrapper.index_source = index_source
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            source_code = handle.read()
        if not source_code.strip():
            warning_logger(f"Empty or whitespace-only file: {path}")
            return _empty_result(path, parser_wrapper.language_name, is_dependency)

        tree = parser_wrapper.parser.parse(bytes(source_code, "utf8"))
        root_node = tree.root_node
        parsed_variables = _parse_variables(
            execute_query(
                parser_wrapper.language, KOTLIN_QUERIES["variables"], root_node
            ),
            source_code,
            path,
            parser_wrapper.language_name,
        )
        parsed_functions = _parse_functions(
            execute_query(
                parser_wrapper.language, KOTLIN_QUERIES["functions"], root_node
            ),
            source_code,
            path,
            parser_wrapper.language_name,
            index_source,
        )
        parsed_classes = _parse_classes(
            execute_query(
                parser_wrapper.language, KOTLIN_QUERIES["classes"], root_node
            ),
            source_code,
            path,
            parser_wrapper.language_name,
            index_source,
        )
        parsed_imports = _parse_imports(
            execute_query(
                parser_wrapper.language, KOTLIN_QUERIES["imports"], root_node
            ),
            source_code,
            parser_wrapper.language_name,
        )
        parsed_calls = _parse_calls(
            execute_query(parser_wrapper.language, KOTLIN_QUERIES["calls"], root_node),
            source_code,
            path,
            parser_wrapper.language_name,
            parsed_variables,
        )
        return {
            "path": str(path),
            "functions": parsed_functions,
            "classes": parsed_classes,
            "variables": parsed_variables,
            "imports": parsed_imports,
            "function_calls": parsed_calls,
            "is_dependency": is_dependency,
            "lang": parser_wrapper.language_name,
        }
    except Exception as exc:
        error_logger(f"Error parsing Kotlin file {path}: {exc}")
        return _empty_result(path, parser_wrapper.language_name, is_dependency)


def pre_scan_kotlin(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Build a name-to-file map for Kotlin declarations."""
    name_to_files: dict[str, list[str]] = {}
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()
            package_name = ""
            match = re.search(r"^\s*package\s+([\w\.]+)", content, re.MULTILINE)
            if match:
                package_name = match.group(1)
            for found in re.finditer(
                r"\b(class|interface|object|typealias)\s+(\w+)", content
            ):
                name = found.group(2)
                name_to_files.setdefault(name, []).append(str(path))
                if package_name:
                    name_to_files.setdefault(f"{package_name}.{name}", []).append(
                        str(path)
                    )
        except Exception:
            continue
    return name_to_files


__all__ = [
    "KOTLIN_QUERIES",
    "KotlinTreeSitterParser",
    "parse_kotlin_file",
    "pre_scan_kotlin",
]
