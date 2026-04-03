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
            if current.type in ("class", "instance"):
                name_node = current.child_by_field_name("name")
                name = self._get_node_text(name_node) if name_node else None
                return (name, current.type, current.start_point[0] + 1)
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
        """Parse Haskell function and bind declarations."""
        functions: list[dict[str, Any]] = []
        seen_nodes: set[int] = set()

        for node, capture_name in captures:
            if capture_name == "name":
                func_node = node.parent
                if func_node is None:
                    continue
                key = func_node.start_byte
                if key in seen_nodes:
                    continue
                seen_nodes.add(key)

                try:
                    func_name = self._get_node_text(node)
                    # Extract parameter names from patterns after the name
                    parameters: list[str] = []
                    for child in func_node.children:
                        if child.type == "patterns":
                            for pat in child.children:
                                if pat.type == "variable":
                                    parameters.append(self._get_node_text(pat))

                    context_name, context_type, _ = self._get_parent_context(func_node)
                    functions.append(
                        {
                            "name": func_name,
                            "args": parameters,
                            "line_number": func_node.start_point[0] + 1,
                            "end_line": func_node.end_point[0] + 1,
                            "path": str(path),
                            "lang": self.language_name,
                            "context": context_name,
                            "class_context": (
                                context_name
                                if context_type and "class" in context_type
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
