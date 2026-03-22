"""JavaScript parser query constants and pre-scan helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import warning_logger
from platform_context_graph.utils.source_text import read_source_text
from platform_context_graph.utils.tree_sitter_manager import execute_query

JS_QUERIES = {
    "functions": """
        (function_declaration 
            name: (identifier) @name
            parameters: (formal_parameters) @params
        ) @function_node
        (variable_declarator 
            name: (identifier) @name 
            value: (function_expression 
                parameters: (formal_parameters) @params
            ) @function_node
        )
        (variable_declarator 
            name: (identifier) @name 
            value: (arrow_function 
                parameters: (formal_parameters) @params
            ) @function_node
        )
        (variable_declarator 
            name: (identifier) @name 
            value: (arrow_function 
                parameter: (identifier) @single_param
            ) @function_node
        )
        (method_definition 
            name: (property_identifier) @name
            parameters: (formal_parameters) @params
        ) @function_node
        (assignment_expression
            left: (member_expression 
                property: (property_identifier) @name
            )
            right: (function_expression
                parameters: (formal_parameters) @params
            ) @function_node
        )
        (assignment_expression
            left: (member_expression 
                property: (property_identifier) @name
            )
            right: (arrow_function
                parameters: (formal_parameters) @params
            ) @function_node
        )
    """,
    "classes": """
        (class_declaration) @class
        (class) @class
    """,
    "imports": """
        (import_statement) @import
        (call_expression
            function: (identifier) @require_call (#eq? @require_call "require")
        ) @import
    """,
    "calls": """
        (call_expression function: (identifier) @name)
        (call_expression function: (member_expression property: (property_identifier) @name))
        (new_expression constructor: (identifier) @name)
        (new_expression constructor: (member_expression property: (property_identifier) @name))
    """,
    "variables": """
        (variable_declarator name: (identifier) @name)
    """,
}


def pre_scan_javascript(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Build a name-to-file map for JavaScript declarations."""
    imports_map: dict[str, list[str]] = {}
    query_str = """
        (class_declaration name: (identifier) @name)
        (function_declaration name: (identifier) @name)
        (variable_declarator name: (identifier) @name value: (function_expression))
        (variable_declarator name: (identifier) @name value: (arrow_function))
        (method_definition name: (property_identifier) @name)
        (assignment_expression
            left: (member_expression 
                property: (property_identifier) @name
            )
            right: (function_expression)
        )
        (assignment_expression
            left: (member_expression 
                property: (property_identifier) @name
            )
            right: (arrow_function)
        )
    """
    for path in files:
        try:
            source_code = read_source_text(path)
            tree = parser_wrapper.parser.parse(bytes(source_code, "utf8"))
            for capture, _ in execute_query(
                parser_wrapper.language, query_str, tree.root_node
            ):
                name = capture.text.decode("utf-8")
                imports_map.setdefault(name, []).append(str(path.resolve()))
        except Exception as exc:
            warning_logger(f"Tree-sitter pre-scan failed for {path}: {exc}")
    return imports_map


__all__ = ["JS_QUERIES", "pre_scan_javascript"]
