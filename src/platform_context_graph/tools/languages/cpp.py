"""C++ tree-sitter parser compatibility facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from platform_context_graph.utils.debug_log import warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

from . import cpp_support as _cpp_support
from .cpp_support import parse_cpp_file

CPP_QUERIES = {
    "functions": """
        (function_definition
            declarator: (function_declarator
                declarator: [
                    (identifier) @name
                    (field_identifier) @name
                ]
            )
        ) @function_node
    """,
    "classes": """
        (class_specifier
            name: (type_identifier) @name
        ) @class
    """,
    "imports": """
        (preproc_include
            path: [
                (string_literal) @path
                (system_lib_string) @path
            ]
        ) @import
    """,
    "calls": """
        (call_expression
            function: [
                (identifier) @function_name
                (field_expression
                    field: (field_identifier) @method_name
                )
            ]
        arguments: (argument_list) @args
    )
    """,
    "enums": """
        (enum_specifier
            name: (type_identifier) @name
            body: (enumerator_list
                (enumerator
                    name: (identifier) @value
                    )*
                )? @body
        ) @enum
    """,
    "structs": """
        (struct_specifier
            name: (type_identifier) @name
            body: (field_declaration_list)? @body
        ) @struct
    """,
    "unions": """
    (union_specifier
    name: (type_identifier)? @name
    body: (field_declaration_list
        (field_declaration
            declarator: [
                (field_identifier) @value
                (pointer_declarator (field_identifier) @value)
                (array_declarator (field_identifier) @value)
                ]
            )*
        )? @body
    ) @union
    """,
    "macros": """
        (preproc_def
            name: (identifier) @name
        ) @macro
    """,
    "variables": """
    (declaration
        declarator: (init_declarator
                        declarator: (identifier) @name))

    (declaration
        declarator: (init_declarator
                        declarator: (pointer_declarator
                            declarator: (identifier) @name)))

    (field_declaration
        declarator: [
             (field_identifier) @name
             (pointer_declarator declarator: (field_identifier) @name)
             (array_declarator declarator: (field_identifier) @name)
             (reference_declarator (field_identifier) @name)
        ]
    )
    """,
    "lambda_assignments": """
    ; Match a lambda assigned to a variable
    (declaration
        declarator: (init_declarator
            declarator: (identifier) @name
            value: (lambda_expression) @lambda_node))
    """,
}

_cpp_support.CPP_QUERIES = CPP_QUERIES


class CppTreeSitterParser:
    """Parse C++ source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Initialize the parser facade.

        Args:
            generic_parser_wrapper: Wrapper object providing parser and language.
        """
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "cpp"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def parse(
        self,
        path: Path,
        is_dependency: bool = False,
        index_source: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Parse one C++ file."""
        del kwargs
        return parse_cpp_file(
            self, path, is_dependency=is_dependency, index_source=index_source
        )


def pre_scan_cpp(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Pre-scan C++ files to map top-level names to file paths."""
    imports_map: dict[str, list[str]] = {}
    query_str = """
        (class_specifier name: (type_identifier) @name)
        (struct_specifier name: (type_identifier) @name)
        (function_definition declarator: (function_declarator declarator: (identifier) @name))
    """

    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                tree = parser_wrapper.parser.parse(handle.read().encode("utf-8"))

            for node, capture_name in execute_query(
                parser_wrapper.language, query_str, tree.root_node
            ):
                if capture_name == "name":
                    imports_map.setdefault(node.text.decode("utf-8"), []).append(
                        str(path.resolve())
                    )
        except Exception as exc:
            warning_logger(f"Tree-sitter pre-scan failed for {path}: {exc}")

    return imports_map


__all__ = ["CppTreeSitterParser", "pre_scan_cpp"]
