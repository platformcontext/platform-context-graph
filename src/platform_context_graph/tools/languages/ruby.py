"""Compatibility facade for the handwritten Ruby parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

from .ruby_support import (
    RUBY_QUERIES,
    find_ruby_module_inclusions,
    find_ruby_modules,
    get_ruby_enclosing_class_name,
    get_ruby_node_text,
    get_ruby_parent_context,
    pre_scan_ruby,
)


class RubyTreeSitterParser:
    """Parse Ruby source files into the graph-friendly document shape."""

    def __init__(self, generic_parser_wrapper: Any):
        """Store the Tree-sitter wrapper used for Ruby parsing.

        Args:
            generic_parser_wrapper: Wrapper that provides language and parser objects.
        """
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "ruby"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def parse(
        self, path: Path, is_dependency: bool = False, index_source: bool = False
    ) -> dict[str, Any]:
        """Parse one Ruby file into the normalized parser payload.

        Args:
            path: Source file path.
            is_dependency: Whether the file belongs to dependency-owned source.
            index_source: Whether parsed nodes should include source text.

        Returns:
            Standardized parsed metadata for the file.
        """
        try:
            self.index_source = index_source
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                source_code = handle.read()

            if not source_code.strip():
                warning_logger(f"Empty or whitespace-only file: {path}")
                return self._empty_result(path, is_dependency)

            tree = self.parser.parse(bytes(source_code, "utf8"))
            root_node = tree.root_node

            parsed_functions: list[dict[str, Any]] = self._parse_functions(
                execute_query(self.language, RUBY_QUERIES["functions"], root_node),
                path,
            )
            parsed_classes: list[dict[str, Any]] = self._parse_classes(
                execute_query(self.language, RUBY_QUERIES["classes"], root_node),
                path,
            )
            parsed_modules = find_ruby_modules(
                root_node,
                language=self.language,
                language_name=self.language_name,
                index_source=self.index_source,
            )
            parsed_imports = self._parse_imports(
                execute_query(self.language, RUBY_QUERIES["imports"], root_node)
            )
            parsed_calls = self._parse_calls(
                execute_query(self.language, RUBY_QUERIES["calls"], root_node),
                path,
            )
            parsed_variables = self._parse_variables(
                execute_query(self.language, RUBY_QUERIES["variables"], root_node),
                path,
            )
            module_inclusions = find_ruby_module_inclusions(
                root_node,
                language=self.language,
                language_name=self.language_name,
            )

            return {
                "path": str(path),
                "functions": parsed_functions,
                "classes": parsed_classes,
                "modules": parsed_modules,
                "module_inclusions": module_inclusions,
                "variables": parsed_variables,
                "imports": parsed_imports,
                "function_calls": parsed_calls,
                "is_dependency": is_dependency,
                "lang": self.language_name,
            }
        except Exception as exc:
            error_logger(f"Error parsing Ruby file {path}: {exc}")
            return self._empty_result(path, is_dependency)

    def _empty_result(self, path: Path, is_dependency: bool) -> dict[str, Any]:
        """Return the standard empty parse result for Ruby files.

        Args:
            path: File path that could not be parsed.
            is_dependency: Whether the file belongs to dependency-owned source.

        Returns:
            Empty parser payload for the file.
        """
        return {
            "path": str(path),
            "functions": [],
            "classes": [],
            "modules": [],
            "module_inclusions": [],
            "variables": [],
            "imports": [],
            "function_calls": [],
            "is_dependency": is_dependency,
            "lang": self.language_name,
        }

    def _get_node_text(self, node: Any) -> str:
        """Decode a tree-sitter node to UTF-8 text.

        Args:
            node: Tree-sitter node to decode.

        Returns:
            Decoded node text, or an empty string when the node is missing.
        """
        return get_ruby_node_text(node)

    def _get_parent_context(
        self, node: Any
    ) -> tuple[str | None, str | None, int | None]:
        """Return the nearest Ruby parent declaration for a node."""
        return get_ruby_parent_context(node)

    def _parse_functions(
        self, captures: list[tuple[Any, str]], path: Path
    ) -> list[dict[str, Any]]:
        """Parse Ruby method declarations."""
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
                name_node = node.child_by_field_name("name")
                if name_node is None:
                    continue

                parameters: list[str] = []
                params_node = node.child_by_field_name("parameters")
                if params_node is not None:
                    for child in params_node.children:
                        if child.type == "identifier":
                            parameters.append(self._get_node_text(child))
                        elif child.type in ("optional_parameter", "required_parameter"):
                            name = child.child_by_field_name("pattern")
                            if name is not None:
                                parameters.append(self._get_node_text(name))

                context_name, context_type, _ = self._get_parent_context(node)
                functions.append(
                    {
                        "name": self._get_node_text(name_node),
                        "parameters": parameters,
                        "args": parameters,
                        "line_number": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "path": str(path),
                        "lang": self.language_name,
                        "context": context_name,
                        "context_type": context_type,
                        "class_context": (
                            context_name
                            if context_type and "class" in context_type
                            else None
                        ),
                    }
                )
            except Exception as exc:
                error_logger(f"Error parsing Ruby method in {path}: {exc}")

        return functions

    def _parse_classes(
        self, captures: list[tuple[Any, str]], path: Path
    ) -> list[dict[str, Any]]:
        """Parse Ruby class declarations."""
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
                name_node = node.child_by_field_name("name")
                if name_node is None:
                    continue

                bases: list[str] = []
                superclass = node.child_by_field_name("superclass")
                if superclass is not None:
                    bases.append(self._get_node_text(superclass))

                classes.append(
                    {
                        "name": self._get_node_text(name_node),
                        "line_number": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "bases": bases,
                        "path": str(path),
                        "lang": self.language_name,
                        "type": "class",
                    }
                )
            except Exception as exc:
                error_logger(f"Error parsing Ruby class in {path}: {exc}")

        return classes

    def _parse_imports(self, captures: list[tuple[Any, str]]) -> list[dict[str, Any]]:
        """Parse Ruby `require` and related import-style calls."""
        imports: list[dict[str, Any]] = []

        for node, capture_name in captures:
            if capture_name != "import":
                continue

            method_node = None
            arguments_node = None
            for child in node.children:
                if child.type == "identifier":
                    method_node = child
                elif child.type == "argument_list":
                    arguments_node = child

            if method_node is None or self._get_node_text(method_node) != "require":
                continue
            if arguments_node is None or not arguments_node.children:
                continue

            string_node = next(
                (child for child in arguments_node.children if child.type == "string"),
                None,
            )
            if string_node is None:
                continue

            source = self._get_node_text(string_node).strip("'\"")
            imports.append(
                {
                    "name": source,
                    "full_import_name": source,
                    "line_number": node.start_point[0] + 1,
                    "alias": None,
                    "context": (None, None),
                    "lang": self.language_name,
                    "is_dependency": False,
                }
            )

        return imports

    def _parse_calls(
        self, captures: list[tuple[Any, str]], path: Path
    ) -> list[dict[str, Any]]:
        """Parse Ruby method and constructor calls."""
        calls: list[dict[str, Any]] = []
        seen_calls: set[tuple[str, int]] = set()

        for node, capture_name in captures:
            if capture_name != "call_node":
                continue

            try:
                method_node = node.child_by_field_name("method")
                if method_node is None:
                    continue

                call_name = self._get_node_text(method_node)
                full_name = call_name
                receiver_node = node.child_by_field_name("receiver")
                if receiver_node is not None:
                    full_name = f"{self._get_node_text(receiver_node)}.{call_name}"

                line_number = node.start_point[0] + 1
                call_key = (full_name, line_number)
                if call_key in seen_calls:
                    continue
                seen_calls.add(call_key)

                args_node = node.child_by_field_name("arguments")
                args = [
                    self._get_node_text(child)
                    for child in (args_node.children if args_node else [])
                    if child.type not in ("(", ")", ",")
                ]
                context_name, context_type, context_line = self._get_parent_context(
                    node
                )
                calls.append(
                    {
                        "name": call_name,
                        "full_name": full_name,
                        "line_number": line_number,
                        "args": args,
                        "inferred_obj_type": None,
                        "context": (context_name, context_type, context_line),
                        "class_context": (
                            (context_name, context_line)
                            if context_type and "class" in context_type
                            else (None, None)
                        ),
                        "lang": self.language_name,
                        "is_dependency": False,
                    }
                )
            except Exception as exc:
                error_logger(f"Error parsing Ruby call in {path}: {exc}")

        return calls

    def _parse_variables(
        self, captures: list[tuple[Any, str]], path: Path
    ) -> list[dict[str, Any]]:
        """Parse Ruby variable and assignment expressions."""
        variables: list[dict[str, Any]] = []
        seen_vars: set[tuple[int, int]] = set()

        for node, capture_name in captures:
            if capture_name != "name":
                continue

            parent = node.parent
            if parent is None or parent.type != "assignment":
                continue

            node_id = (node.start_byte, node.end_byte)
            if node_id in seen_vars:
                continue
            seen_vars.add(node_id)

            var_name = self._get_node_text(node)
            value_node = parent.child_by_field_name("right")
            inferred_type = "Unknown"
            if value_node is not None:
                inferred_type = self._get_node_text(value_node)
                if inferred_type.startswith("new "):
                    inferred_type = inferred_type.removeprefix("new ").split("(")[0]

            context_name, context_type, _ = self._get_parent_context(node)
            variables.append(
                {
                    "name": var_name,
                    "type": inferred_type,
                    "line_number": node.start_point[0] + 1,
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

        return variables


__all__ = ["RubyTreeSitterParser", "pre_scan_ruby"]
