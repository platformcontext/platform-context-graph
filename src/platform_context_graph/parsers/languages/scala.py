"""Compatibility facade for the handwritten Scala parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

from .scala_support import (
    SCALA_QUERIES,
    _extract_parameter_names,
    _parse_calls,
    _parse_classes,
    _parse_imports,
    _parse_functions,
    _parse_variables,
    pre_scan_scala,
)


class ScalaTreeSitterParser:
    """Parse Scala source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Store the parser wrapper used for Scala parsing."""
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "scala"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def parse(
        self, path: Path, is_dependency: bool = False, index_source: bool = False
    ) -> dict[str, Any]:
        """Parse one Scala file into the normalized parser payload."""
        try:
            self.index_source = index_source
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                source_code = handle.read()
            if not source_code.strip():
                warning_logger(f"Empty or whitespace-only file: {path}")
                return self._empty_result(path, is_dependency)

            tree = self.parser.parse(bytes(source_code, "utf8"))
            root_node = tree.root_node
            parsed_variables = _parse_variables(
                self,
                execute_query(self.language, SCALA_QUERIES["variables"], root_node),
                source_code,
                path,
            )
            parsed_functions = _parse_functions(
                self,
                execute_query(self.language, SCALA_QUERIES["functions"], root_node),
                source_code,
                path,
            )
            parsed_classes = _parse_classes(
                self,
                execute_query(self.language, SCALA_QUERIES["classes"], root_node),
                source_code,
                path,
            )
            parsed_imports = _parse_imports(
                self,
                execute_query(self.language, SCALA_QUERIES["imports"], root_node),
                source_code,
            )
            parsed_calls = _parse_calls(
                self,
                execute_query(self.language, SCALA_QUERIES["calls"], root_node),
                source_code,
                path,
                parsed_variables,
            )

            final_classes: list[dict[str, Any]] = []
            final_traits: list[dict[str, Any]] = []
            for item in parsed_classes:
                item_type = item.get("type", "class")
                if item_type == "trait":
                    final_traits.append(item)
                elif item_type == "object":
                    item["is_object"] = True
                    final_classes.append(item)
                else:
                    final_classes.append(item)

            return {
                "path": str(path),
                "functions": parsed_functions,
                "classes": final_classes,
                "traits": final_traits,
                "variables": parsed_variables,
                "imports": parsed_imports,
                "function_calls": parsed_calls,
                "is_dependency": is_dependency,
                "lang": self.language_name,
            }
        except Exception as exc:
            error_logger(f"Error parsing Scala file {path}: {exc}")
            return self._empty_result(path, is_dependency)

    def _empty_result(self, path: Path, is_dependency: bool) -> dict[str, Any]:
        """Return the standard empty parse result for Scala files."""
        return {
            "path": str(path),
            "functions": [],
            "classes": [],
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
        """Find the nearest enclosing Scala declaration for a node."""
        current = node.parent
        while current:
            if current.type in (
                "function_definition",
                "class_definition",
                "object_definition",
                "trait_definition",
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

    def _extract_parameter_names(self, params_text: str) -> list[str]:
        """Extract Scala parameter names from a parameter list string."""
        return _extract_parameter_names(params_text)


__all__ = ["ScalaTreeSitterParser", "pre_scan_scala"]
