"""Compatibility facade for the handwritten PHP parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

from .php_support import (
    PHP_QUERIES,
    _parse_calls,
    _parse_functions,
    _parse_imports,
    _parse_types,
    _parse_variables,
    pre_scan_php,
)


class PhpTreeSitterParser:
    """Parse PHP source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Store the parser wrapper used for PHP parsing."""
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "php"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def parse(
        self, path: Path, is_dependency: bool = False, index_source: bool = False
    ) -> dict[str, Any]:
        """Parse one PHP file into the normalized parser payload."""
        try:
            self.index_source = index_source
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                source_code = handle.read()

            if not source_code.strip():
                warning_logger(f"Empty or whitespace-only file: {path}")
                return self._empty_result(path, is_dependency)

            tree = self.parser.parse(bytes(source_code, "utf8"))
            root_node = tree.root_node

            parsed_functions = _parse_functions(
                self,
                execute_query(self.language, PHP_QUERIES["functions"], root_node),
                source_code,
                path,
            )
            parsed_classes, parsed_interfaces, parsed_traits = _parse_types(
                self,
                execute_query(self.language, PHP_QUERIES["classes"], root_node),
                source_code,
                path,
            )
            parsed_variables = _parse_variables(
                self,
                execute_query(self.language, PHP_QUERIES["variables"], root_node),
                source_code,
                path,
            )
            parsed_imports = _parse_imports(
                self,
                execute_query(self.language, PHP_QUERIES["imports"], root_node),
                source_code,
            )
            parsed_calls = _parse_calls(
                self,
                execute_query(self.language, PHP_QUERIES["calls"], root_node),
                source_code,
            )

            return {
                "path": str(path),
                "functions": parsed_functions,
                "classes": parsed_classes,
                "interfaces": parsed_interfaces,
                "traits": parsed_traits,
                "variables": parsed_variables,
                "imports": parsed_imports,
                "function_calls": parsed_calls,
                "is_dependency": is_dependency,
                "lang": self.language_name,
            }
        except Exception as exc:
            error_logger(f"Error parsing PHP file {path}: {exc}")
            return self._empty_result(path, is_dependency)

    def _empty_result(self, path: Path, is_dependency: bool) -> dict[str, Any]:
        """Return the standard empty parse result for PHP files."""
        return {
            "path": str(path),
            "functions": [],
            "classes": [],
            "interfaces": [],
            "traits": [],
            "variables": [],
            "imports": [],
            "function_calls": [],
            "is_dependency": is_dependency,
            "lang": self.language_name,
        }

    def _get_parent_context(
        self, node: Any
    ) -> tuple[str | None, str | None, int | None]:
        """Return the nearest PHP declaration that encloses a node."""
        current = node.parent
        while current:
            if current.type in (
                "function_definition",
                "method_declaration",
                "class_declaration",
                "interface_declaration",
                "trait_declaration",
            ):
                name_node = current.child_by_field_name("name")
                return (
                    self._get_node_text(name_node) if name_node else None,
                    current.type,
                    current.start_point[0] + 1,
                )
            current = current.parent
        return None, None, None

    def _get_node_text(self, node: Any) -> str:
        """Decode a tree-sitter node to UTF-8 text."""
        if not node:
            return ""
        return node.text.decode("utf-8")


__all__ = ["PhpTreeSitterParser", "pre_scan_php"]
