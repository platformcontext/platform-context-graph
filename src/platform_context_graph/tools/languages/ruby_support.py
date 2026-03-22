"""Support constants and helper functions for the Ruby tree-sitter parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

RUBY_QUERIES = {
    "functions": """
        (method
            name: (identifier) @name
        ) @function_node
    """,
    "classes": """
        (class
            name: (constant) @name
        ) @class
    """,
    "modules": """
        (module
            name: (constant) @name
        ) @module_node
    """,
    "imports": """
        (call
            method: (identifier) @method_name
            arguments: (argument_list
                (string) @path
            )
        ) @import
    """,
    "calls": """
        (call
            receiver: (_)? @receiver
            method: (identifier) @name
            arguments: (argument_list)? @args
        ) @call_node
    """,
    "variables": """
        (assignment
            left: (identifier) @name
            right: (_) @value
        )
        (assignment
            left: (instance_variable) @name
            right: (_) @value
        )
    """,
    "comments": """
        (comment) @comment
    """,
    "module_includes": """
        (call
          method: (identifier) @method
          arguments: (argument_list (constant) @module)
        ) @include_call
    """,
}


def get_ruby_node_text(node: Any) -> str:
    """Decode a tree-sitter node as UTF-8 text.

    Args:
        node: Tree-sitter node to decode.

    Returns:
        Decoded node text.
    """
    return node.text.decode("utf-8")


def get_ruby_parent_context(
    node: Any, types: tuple[str, ...] = ("class", "module", "method")
) -> tuple[str | None, str | None, int | None]:
    """Find the nearest Ruby parent context that matches the given node types.

    Args:
        node: Tree-sitter node whose parent context is needed.
        types: Parent node types to match.

    Returns:
        Tuple of context name, context type, and 1-based line number.
    """
    current = node.parent
    while current:
        if current.type in types:
            name_node = current.child_by_field_name("name")
            if name_node:
                return (
                    get_ruby_node_text(name_node),
                    current.type,
                    current.start_point[0] + 1,
                )
        current = current.parent
    return None, None, None


def get_ruby_enclosing_class_name(node: Any) -> str | None:
    """Find the nearest enclosing Ruby class or module name.

    Args:
        node: Tree-sitter node whose enclosing class is needed.

    Returns:
        Enclosing class or module name when present.
    """
    name, _, _ = get_ruby_parent_context(node, ("class",))
    return name


def find_ruby_modules(
    root_node: Any,
    *,
    language: Any,
    language_name: str,
    index_source: bool,
) -> list[dict[str, Any]]:
    """Find Ruby module declarations from the parsed tree.

    Args:
        root_node: Tree-sitter root node.
        language: Tree-sitter language object.
        language_name: Language label to attach to results.
        index_source: Whether to include raw source text in results.

    Returns:
        Parsed module entries.
    """
    modules: list[dict[str, Any]] = []
    captures = list(execute_query(language, RUBY_QUERIES["modules"], root_node))
    for node, capture_name in captures:
        if capture_name != "module_node":
            continue

        name = None
        for candidate, candidate_name in captures:
            if candidate_name != "name":
                continue
            if (
                candidate.start_byte >= node.start_byte
                and candidate.end_byte <= node.end_byte
            ):
                name = get_ruby_node_text(candidate)
                break
        if not name:
            continue

        module_data: dict[str, Any] = {
            "name": name,
            "line_number": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "lang": language_name,
            "is_dependency": False,
        }
        if index_source:
            module_data["source"] = get_ruby_node_text(node)
        modules.append(module_data)
    return modules


def find_ruby_module_inclusions(
    root_node: Any,
    *,
    language: Any,
    language_name: str,
) -> list[dict[str, Any]]:
    """Find `include` calls that mix modules into Ruby classes.

    Args:
        root_node: Tree-sitter root node.
        language: Tree-sitter language object.
        language_name: Language label to attach to results.

    Returns:
        Parsed module inclusion entries.
    """
    includes: list[dict[str, Any]] = []
    query = RUBY_QUERIES["module_includes"]
    for node, capture_name in execute_query(language, query, root_node):
        if capture_name == "method":
            if get_ruby_node_text(node) != "include":
                continue
        if capture_name != "include_call":
            continue

        method = None
        module = None
        for child, child_capture in execute_query(language, query, node):
            if child_capture == "method":
                method = get_ruby_node_text(child)
            elif child_capture == "module":
                module = get_ruby_node_text(child)
        if method != "include" or not module:
            continue

        enclosing_class = get_ruby_enclosing_class_name(node)
        if enclosing_class:
            includes.append(
                {
                    "class": enclosing_class,
                    "module": module,
                    "line_number": node.start_point[0] + 1,
                    "lang": language_name,
                    "is_dependency": False,
                }
            )
    return includes


def pre_scan_ruby(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Build a name-to-file map for Ruby classes, modules, and methods.

    Args:
        files: Ruby files to scan.
        parser_wrapper: Wrapper providing a parser and language.

    Returns:
        Mapping of discovered names to the files that define them.
    """
    imports_map: dict[str, list[str]] = {}
    query = """
        (class
            name: (constant) @name
        )
        (module
            name: (constant) @name
        )
        (method
            name: (identifier) @name
        )
    """

    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                tree = parser_wrapper.parser.parse(bytes(handle.read(), "utf8"))

            for capture, _ in execute_query(
                parser_wrapper.language, query, tree.root_node
            ):
                name = capture.text.decode("utf-8")
                imports_map.setdefault(name, []).append(str(path.resolve()))
        except Exception as exc:
            warning_logger(f"Tree-sitter pre-scan failed for {path}: {exc}")

    return imports_map
