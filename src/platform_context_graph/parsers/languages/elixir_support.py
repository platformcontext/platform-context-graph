"""Elixir parser support constants and pre-scan helpers."""

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import warning_logger

ELIXIR_QUERIES = {
    "modules": """
        (call
            target: (identifier) @keyword
            (arguments (alias) @name)
            (do_block)
        ) @module_node
    """,
    "functions": """
        (call
            target: (identifier) @keyword
            (arguments
                (call
                    target: (identifier) @name
                )
            )
        ) @function_node
    """,
    "imports": """
        (call
            target: (identifier) @keyword
            (arguments (alias) @path)
        ) @import_node
    """,
    "calls": """
        (call
            target: (dot
                left: (_) @receiver
                right: (identifier) @name
            )
            (arguments) @args
        ) @call_node
    """,
    "simple_calls": """
        (call
            target: (identifier) @name
            (arguments) @args
        ) @call_node
    """,
    "module_attributes": """
        (unary_operator
            operator: "@"
            operand: (call
                target: (identifier) @attr_name
                (arguments (_) @attr_value)
            )
        ) @attribute
    """,
    "comments": """
        (comment) @comment
    """,
}

MODULE_KEYWORDS = {"defmodule", "defprotocol", "defimpl"}
FUNCTION_KEYWORDS = {
    "def",
    "defp",
    "defmacro",
    "defmacrop",
    "defguard",
    "defguardp",
    "defdelegate",
}
IMPORT_KEYWORDS = {"use", "import", "alias", "require"}
ELIXIR_KEYWORDS = (
    MODULE_KEYWORDS
    | FUNCTION_KEYWORDS
    | IMPORT_KEYWORDS
    | {
        "quote",
        "unquote",
        "case",
        "cond",
        "if",
        "unless",
        "for",
        "with",
        "try",
        "receive",
        "raise",
        "reraise",
        "throw",
        "super",
    }
)


def pre_scan_elixir(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Build a module-and-function map for Elixir source files.

    Args:
        files: Elixir files to scan.
        parser_wrapper: Wrapper providing a parser instance.

    Returns:
        Mapping of discovered names to the files that define them.
    """
    imports_map: dict[str, list[str]] = {}

    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                source = handle.read()
            tree = parser_wrapper.parser.parse(bytes(source, "utf8"))
            _pre_scan_recursive(tree.root_node, path, imports_map)
        except Exception as exc:
            warning_logger(f"Tree-sitter pre-scan failed for {path}: {exc}")

    return imports_map


def _pre_scan_recursive(
    node: Any, path: Path, imports_map: dict[str, list[str]]
) -> None:
    """Populate the Elixir pre-scan map by walking the tree recursively.

    Args:
        node: Current tree-sitter node.
        path: Source file being scanned.
        imports_map: Mutable output mapping.
    """
    if node.type == "call":
        for child in node.children:
            if child.type != "identifier":
                continue
            keyword = child.text.decode("utf-8")
            if keyword in MODULE_KEYWORDS:
                for sibling in node.children:
                    if sibling.type != "arguments":
                        continue
                    for argument_child in sibling.children:
                        if argument_child.type == "alias":
                            name = argument_child.text.decode("utf-8")
                            imports_map.setdefault(name, []).append(str(path.resolve()))
            elif keyword in FUNCTION_KEYWORDS:
                for sibling in node.children:
                    if sibling.type != "arguments":
                        continue
                    for argument_child in sibling.children:
                        if argument_child.type == "call":
                            target = argument_child.child_by_field_name("target")
                            if target:
                                name = target.text.decode("utf-8")
                                imports_map.setdefault(name, []).append(
                                    str(path.resolve())
                                )
            break

    for child in node.children:
        _pre_scan_recursive(child, path, imports_map)
