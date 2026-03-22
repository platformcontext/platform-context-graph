"""C tree-sitter parser compatibility facade."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

from platform_context_graph.utils.debug_log import warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

from .c_support import parse_c_file


class CTreeSitterParser:
    """Parse C source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Initialize the parser facade.

        Args:
            generic_parser_wrapper: Wrapper object providing parser and language.
        """
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "c"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def parse(
        self, path: Path, is_dependency: bool = False, index_source: bool = False
    ) -> Dict[str, Any]:
        """Parse one C file."""
        return parse_c_file(
            self, path, is_dependency=is_dependency, index_source=index_source
        )


def pre_scan_c(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Pre-scan C files to map top-level names to file paths."""
    imports_map: dict[str, list[str]] = {}
    query_str = """
        (function_definition
            declarator: (function_declarator
                declarator: (identifier) @name
            )
        )

        (function_definition
            declarator: (function_declarator
                declarator: (pointer_declarator
                    declarator: (identifier) @name
                )
            )
        )

        (struct_specifier
            name: (type_identifier) @name
        )

        (union_specifier
            name: (type_identifier) @name
        )

        (enum_specifier
            name: (type_identifier) @name
        )

        (type_definition
            declarator: (type_identifier) @name
        )

        (preproc_def
            name: (identifier) @name
        )
    """

    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                tree = parser_wrapper.parser.parse(bytes(handle.read(), "utf8"))

            for capture, _ in execute_query(
                parser_wrapper.language, query_str, tree.root_node
            ):
                name = capture.text.decode("utf-8")
                imports_map.setdefault(name, []).append(str(path.resolve()))
        except Exception as exc:
            warning_logger(f"Tree-sitter pre-scan failed for {path}: {exc}")

    return imports_map


__all__ = ["CTreeSitterParser", "pre_scan_c"]
