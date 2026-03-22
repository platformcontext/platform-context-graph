"""Compatibility facade for the handwritten Haskell parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

from .haskell_support import (
    HASKELL_QUERIES,
    _parse_calls,
    _parse_classes,
    _parse_imports,
    _parse_variables,
    pre_scan_haskell,
)


class HaskellTreeSitterParser:
    """Parse Haskell source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Store the parser wrapper used for Haskell parsing."""
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "haskell"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def parse(
        self, path: Path, is_dependency: bool = False, index_source: bool = False
    ) -> dict[str, Any]:
        """Parse one Haskell file into the standard graph payload."""
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
                execute_query(self.language, HASKELL_QUERIES["variables"], root_node),
                source_code,
                path,
            )
            parsed_functions = self._parse_functions(
                execute_query(self.language, HASKELL_QUERIES["functions"], root_node),
                source_code,
                path,
            )
            parsed_classes = _parse_classes(
                self,
                execute_query(self.language, HASKELL_QUERIES["classes"], root_node),
                source_code,
                path,
            )
            parsed_imports = _parse_imports(
                self,
                execute_query(self.language, HASKELL_QUERIES["imports"], root_node),
                source_code,
            )
            parsed_calls = _parse_calls(
                self,
                execute_query(self.language, HASKELL_QUERIES["calls"], root_node),
                source_code,
                path,
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
                "lang": self.language_name,
            }
        except Exception as exc:
            error_logger(f"Error parsing Haskell file {path}: {exc}")
            return self._empty_result(path, is_dependency)

    def _empty_result(self, path: Path, is_dependency: bool) -> dict[str, Any]:
        """Return the standard empty parse result for Haskell files."""
        return {
            "path": str(path),
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
            "function_calls": [],
            "is_dependency": is_dependency,
            "lang": self.language_name,
        }

    def _get_parent_context(
        self, node: Any
    ) -> tuple[str | None, str | None, int | None]:
        """Find the nearest enclosing declaration for a Haskell node."""
        current = node.parent
        while current:
            if current.type in ("class_declaration",):
                for child in current.children:
                    if child.type == "simple_identifier":
                        return (
                            self._get_node_text(child),
                            current.type,
                            current.start_point[0] + 1,
                        )
                return (None, current.type, current.start_point[0] + 1)
            if current.type in ("class_declaration", "object_declaration"):
                for child in current.children:
                    if child.type in ("simple_identifier", "type_identifier"):
                        return (
                            self._get_node_text(child),
                            current.type,
                            current.start_point[0] + 1,
                        )
            if current.type == "secondary_constructor":
                return ("constructor", current.type, current.start_point[0] + 1)
            if current.type == "companion_object":
                name = "Companion"
                for child in current.children:
                    if child.type in ("simple_identifier", "type_identifier"):
                        name = self._get_node_text(child)
                        break
                return (name, current.type, current.start_point[0] + 1)
            if current.type == "object_literal":
                return ("AnonymousObject", current.type, current.start_point[0] + 1)
            current = current.parent
        return None, None, None

    def _get_node_text(self, node: Any) -> str:
        """Decode a tree-sitter node to text."""
        if not node:
            return ""
        return node.text.decode("utf-8")

    def _parse_functions(
        self, captures: list[tuple[Any, str]], source_code: str, path: Path
    ) -> list[dict[str, Any]]:
        """Parse Haskell function and initializer declarations."""
        functions: list[dict[str, Any]] = []
        seen_nodes: set[tuple[int, int, str]] = set()

        for node, capture_name in captures:
            if capture_name not in ("function_node", "init_node"):
                continue
            node_id = (node.start_byte, node.end_byte, node.type)
            if node_id in seen_nodes:
                continue
            seen_nodes.add(node_id)

            try:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1

                name_node = None
                for child in node.children:
                    if child.type == "simple_identifier":
                        name_node = child
                        break
                if name_node is None and capture_name == "init_node":
                    name_node = node.child_by_field_name("name")
                if name_node is None:
                    continue

                params_node = None
                for child in node.children:
                    if child.type == "function_value_parameters":
                        params_node = child
                        break
                parameters: list[str] = []
                if params_node is not None:
                    parameters = [
                        self._get_node_text(child)
                        for child in params_node.children
                        if child.type == "simple_identifier"
                    ]

                context_name, context_type, _ = self._get_parent_context(node)
                functions.append(
                    {
                        "name": self._get_node_text(name_node),
                        "args": parameters,
                        "line_number": start_line,
                        "end_line": end_line,
                        "path": str(path),
                        "lang": self.language_name,
                        "context": context_name,
                        "class_context": (
                            context_name
                            if context_type
                            and ("class" in context_type or "object" in context_type)
                            else None
                        ),
                    }
                )
                if self.index_source:
                    functions[-1]["source"] = source_code
            except Exception as exc:
                error_logger(f"Error parsing function in {path}: {exc}")

        return functions


__all__ = ["HaskellTreeSitterParser", "pre_scan_haskell"]
