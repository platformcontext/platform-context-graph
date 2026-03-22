"""Support helpers for the handwritten JavaScript parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import warning_logger
from platform_context_graph.utils.source_text import read_source_text
from platform_context_graph.utils.tree_sitter_manager import execute_query
from .javascript_support_queries import JS_QUERIES, pre_scan_javascript
from .javascript_support_helpers import (
    classify_method_kind as _classify_method_kind,
    empty_result as _empty_result,
    extract_parameters as _extract_parameters,
    find_function_node_for_name as _find_function_node_for_name,
    find_function_node_for_params as _find_function_node_for_params,
    first_line_before_body as _first_line_before_body,
    get_jsdoc_comment as _get_jsdoc_comment,
    get_parent_context as _get_parent_context,
    node_text as _get_node_text,
)


def _find_functions(
    language: Any,
    root_node: Any,
    language_name: str,
    index_source: bool,
) -> list[dict[str, Any]]:
    """Parse JavaScript function-like declarations from a syntax tree."""
    functions: list[dict[str, Any]] = []
    query_str = JS_QUERIES["functions"]
    captures_by_function: dict[tuple[int, int, str], dict[str, Any]] = {}

    for node, capture_name in execute_query(language, query_str, root_node):
        if capture_name == "function_node":
            function_node = node
        elif capture_name == "name":
            function_node = _find_function_node_for_name(node)
        else:
            function_node = _find_function_node_for_params(node)
        if function_node is None:
            continue
        key = (function_node.start_byte, function_node.end_byte, function_node.type)
        bucket = captures_by_function.setdefault(
            key,
            {"node": function_node, "name": None, "params": None, "single_param": None},
        )
        if capture_name == "name":
            bucket["name"] = _get_node_text(node)
        elif capture_name == "params":
            bucket["params"] = node
        elif capture_name == "single_param":
            bucket["single_param"] = node

    for data in captures_by_function.values():
        func_node = data["node"]
        name = data["name"]
        if not name and func_node.type == "method_definition":
            name_node = func_node.child_by_field_name("name")
            if name_node:
                name = _get_node_text(name_node)
        if not name:
            continue

        args: list[str] = []
        if data["params"] is not None:
            args = _extract_parameters(data["params"], _get_node_text)
        elif data["single_param"] is not None:
            args = [_get_node_text(data["single_param"])]

        js_kind = None
        if func_node.type == "method_definition":
            js_kind = _classify_method_kind(
                _first_line_before_body(_get_node_text(func_node))
            )

        func_data = {
            "name": name,
            "line_number": func_node.start_point[0] + 1,
            "end_line": func_node.end_point[0] + 1,
            "args": args,
            "lang": language_name,
            "is_dependency": False,
        }
        if index_source:
            func_data["source"] = _get_node_text(func_node)
            func_data["docstring"] = _get_jsdoc_comment(func_node, _get_node_text)
        if js_kind is not None:
            func_data["type"] = js_kind
        functions.append(func_data)

    return functions


def _find_classes(
    language: Any,
    root_node: Any,
    language_name: str,
    index_source: bool,
) -> list[dict[str, Any]]:
    """Parse JavaScript class declarations from a syntax tree."""
    classes: list[dict[str, Any]] = []
    for class_node, capture_name in execute_query(
        language, JS_QUERIES["classes"], root_node
    ):
        if capture_name != "class":
            continue
        name_node = class_node.child_by_field_name("name")
        if not name_node:
            continue
        bases: list[str] = []
        heritage_node = next(
            (child for child in class_node.children if child.type == "class_heritage"),
            None,
        )
        if heritage_node:
            if heritage_node.named_child_count > 0:
                bases.append(_get_node_text(heritage_node.named_child(0)))
            elif heritage_node.child_count > 0:
                bases.append(
                    _get_node_text(heritage_node.child(heritage_node.child_count - 1))
                )

        class_data = {
            "name": _get_node_text(name_node),
            "line_number": class_node.start_point[0] + 1,
            "end_line": class_node.end_point[0] + 1,
            "bases": bases,
            "context": None,
            "decorators": [],
            "lang": language_name,
            "is_dependency": False,
        }
        if index_source:
            class_data["source"] = _get_node_text(class_node)
            class_data["docstring"] = None
        classes.append(class_data)
    return classes


def _find_imports(
    language: Any, root_node: Any, language_name: str
) -> list[dict[str, Any]]:
    """Parse JavaScript import statements and CommonJS requires."""
    imports: list[dict[str, Any]] = []
    for node, capture_name in execute_query(language, JS_QUERIES["imports"], root_node):
        if capture_name != "import":
            continue
        line_number = node.start_point[0] + 1
        if node.type == "import_statement":
            source_node = node.child_by_field_name("source")
            if source_node is None:
                continue
            source = _get_node_text(source_node).strip("'\"")
            import_clause = node.child_by_field_name("import")
            if not import_clause:
                imports.append(
                    {
                        "name": source,
                        "source": source,
                        "alias": None,
                        "line_number": line_number,
                        "lang": language_name,
                    }
                )
                continue
            if import_clause.type == "identifier":
                imports.append(
                    {
                        "name": "default",
                        "source": source,
                        "alias": _get_node_text(import_clause),
                        "line_number": line_number,
                        "lang": language_name,
                    }
                )
            elif import_clause.type == "namespace_import":
                alias_node = import_clause.child_by_field_name("alias")
                if alias_node:
                    imports.append(
                        {
                            "name": "*",
                            "source": source,
                            "alias": _get_node_text(alias_node),
                            "line_number": line_number,
                            "lang": language_name,
                        }
                    )
            elif import_clause.type == "named_imports":
                for specifier in import_clause.children:
                    if specifier.type != "import_specifier":
                        continue
                    name_node = specifier.child_by_field_name("name")
                    if not name_node:
                        continue
                    alias_node = specifier.child_by_field_name("alias")
                    imports.append(
                        {
                            "name": _get_node_text(name_node),
                            "source": source,
                            "alias": _get_node_text(alias_node) if alias_node else None,
                            "line_number": line_number,
                            "lang": language_name,
                        }
                    )
        elif node.type == "call_expression":
            args = node.child_by_field_name("arguments")
            if not args or args.named_child_count == 0:
                continue
            source_node = args.named_child(0)
            if not source_node or source_node.type != "string":
                continue
            source = _get_node_text(source_node).strip("'\"")
            alias = None
            if node.parent.type == "variable_declarator":
                alias_node = node.parent.child_by_field_name("name")
                if alias_node:
                    alias = _get_node_text(alias_node)
            imports.append(
                {
                    "name": source,
                    "source": source,
                    "alias": alias,
                    "line_number": line_number,
                    "lang": language_name,
                }
            )
    return imports


def _find_calls(
    language: Any, root_node: Any, language_name: str
) -> list[dict[str, Any]]:
    """Parse JavaScript call expressions from a syntax tree."""
    calls: list[dict[str, Any]] = []
    for node, capture_name in execute_query(language, JS_QUERIES["calls"], root_node):
        if capture_name != "name":
            continue
        call_node = node.parent
        while call_node and call_node.type not in (
            "call_expression",
            "new_expression",
            "program",
        ):
            call_node = call_node.parent

        name = _get_node_text(node)
        args: list[str] = []
        arguments_node = None
        if call_node and call_node.type in ("call_expression", "new_expression"):
            arguments_node = call_node.child_by_field_name("arguments")
        if arguments_node:
            for arg in arguments_node.children:
                if arg.type not in ("(", ")", ","):
                    args.append(_get_node_text(arg))

        calls.append(
            {
                "name": name,
                "full_name": _get_node_text(call_node) if call_node else name,
                "line_number": node.start_point[0] + 1,
                "args": args,
                "inferred_obj_type": None,
                "context": _get_parent_context(node, _get_node_text),
                "class_context": _get_parent_context(
                    node, _get_node_text, types=("class_declaration",)
                )[:2],
                "lang": language_name,
                "is_dependency": False,
            }
        )
    return calls


def _find_variables(
    language: Any, root_node: Any, language_name: str
) -> list[dict[str, Any]]:
    """Parse JavaScript variable declarations from a syntax tree."""
    variables: list[dict[str, Any]] = []
    for node, capture_name in execute_query(
        language, JS_QUERIES["variables"], root_node
    ):
        if capture_name != "name":
            continue
        var_node = node.parent
        name = _get_node_text(node)
        value = None
        type_text = None
        value_node = var_node.child_by_field_name("value") if var_node else None
        if value_node:
            value_type = value_node.type
            if (
                value_type in ("function_expression", "arrow_function")
                or "function" in value_type
                or "arrow" in value_type
            ):
                continue
            if value_type == "call_expression":
                func_node = value_node.child_by_field_name("function")
                value = _get_node_text(func_node) if func_node else name
            else:
                value = _get_node_text(value_node)
        context, context_type, _ = _get_parent_context(node, _get_node_text)
        variables.append(
            {
                "name": name,
                "line_number": node.start_point[0] + 1,
                "value": value,
                "type": type_text,
                "context": context,
                "class_context": (
                    context if context_type == "class_declaration" else None
                ),
                "lang": language_name,
                "is_dependency": False,
            }
        )
    return variables


class JavascriptTreeSitterParser:
    """Parse JavaScript source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Store the generic parser wrapper used for parsing.

        Args:
            generic_parser_wrapper: Wrapper providing language and parser objects.
        """
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = generic_parser_wrapper.language_name
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser

    def parse(
        self,
        path: Path,
        is_dependency: bool = False,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Parse a JavaScript file into the standard graph-friendly structure."""
        return parse_javascript_file(
            self,
            path,
            is_dependency=is_dependency,
            index_source=index_source,
        )


def parse_javascript_file(
    parser_wrapper: Any,
    path: Path,
    *,
    is_dependency: bool = False,
    index_source: bool = False,
) -> dict[str, Any]:
    """Parse one JavaScript file into the repository graph schema."""
    try:
        parser_wrapper.index_source = index_source
        source_code = read_source_text(path)
        tree = parser_wrapper.parser.parse(bytes(source_code, "utf8"))
        root_node = tree.root_node
        return {
            "path": str(path),
            "functions": _find_functions(
                parser_wrapper.language,
                root_node,
                parser_wrapper.language_name,
                index_source,
            ),
            "classes": _find_classes(
                parser_wrapper.language,
                root_node,
                parser_wrapper.language_name,
                index_source,
            ),
            "variables": _find_variables(
                parser_wrapper.language, root_node, parser_wrapper.language_name
            ),
            "imports": _find_imports(
                parser_wrapper.language, root_node, parser_wrapper.language_name
            ),
            "function_calls": _find_calls(
                parser_wrapper.language, root_node, parser_wrapper.language_name
            ),
            "is_dependency": is_dependency,
            "lang": parser_wrapper.language_name,
        }
    except Exception as exc:
        warning_logger(f"Error parsing JavaScript file {path}: {exc}")
        return _empty_result(path, parser_wrapper.language_name, is_dependency)


__all__ = [
    "JS_QUERIES",
    "JavascriptTreeSitterParser",
    "parse_javascript_file",
    "pre_scan_javascript",
]
