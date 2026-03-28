"""Support helpers for the handwritten Dart parser facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

from .dart_support_calls import find_calls
from .dart_support_queries import DART_QUERIES, PRESCAN_QUERY


def parse_dart_file(
    parser: Any, path: Path, is_dependency: bool = False, index_source: bool = False
) -> dict[str, Any]:
    """Parse one Dart file into the repository's normalized structure."""

    parser.index_source = index_source
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            source_code = handle.read()

        tree = parser.parser.parse(source_code.encode("utf8"))
        root_node = tree.root_node

        return {
            "path": str(path),
            "functions": _find_functions(parser, root_node),
            "classes": _find_classes(parser, root_node),
            "variables": _find_variables(parser, root_node),
            "imports": _find_imports(parser, root_node),
            "function_calls": find_calls(
                root_node=root_node,
                language_name=parser.language_name,
                get_node_text=_get_node_text,
                get_parent_context=_get_parent_context,
                get_declaration_name=_get_declaration_name,
            ),
            "is_dependency": is_dependency,
            "lang": parser.language_name,
        }
    except Exception as exc:
        error_logger(f"Failed to parse Dart file {path}: {exc}")
        return {"path": str(path), "error": str(exc)}


def _get_node_text(node: Any) -> str:
    """Decode source text from a tree-sitter node."""

    if not node:
        return ""
    return node.text.decode("utf-8")


def _get_declaration_name(node: Any):
    """Return the declared identifier for class-like Dart nodes."""

    if node is None:
        return None

    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return name_node

    return next((child for child in node.children if child.type == "identifier"), None)


def _get_signature_context(node: Any):
    """Return the callable declaration metadata for one signature node."""

    if node is None:
        return None, None, None

    candidate = node
    if node.type == "method_signature":
        candidate = next(
            (
                child
                for child in node.children
                if child.type
                in ("function_signature", "constructor_signature", "getter_signature")
            ),
            node,
        )

    if candidate.type not in (
        "function_signature",
        "constructor_signature",
        "getter_signature",
    ):
        return None, None, None

    name_node = _get_declaration_name(candidate)
    if name_node is None:
        return None, None, None

    return (
        _get_node_text(name_node),
        candidate.type,
        candidate.start_point[0] + 1,
    )


def _get_parent_context(
    node: Any,
    types: tuple[str, ...] = (
        "function_signature",
        "method_signature",
        "constructor_signature",
        "getter_signature",
        "class_definition",
        "mixin_declaration",
        "extension_declaration",
    ),
):
    """Return the nearest enclosing Dart declaration."""

    curr = node.parent
    while curr:
        if curr.type == "function_body" and curr.parent is not None:
            named_siblings = [child for child in curr.parent.children if child.is_named]
            try:
                curr_index = named_siblings.index(curr)
            except ValueError:
                curr_index = -1
            if curr_index > 0:
                for sibling in reversed(named_siblings[:curr_index]):
                    signature_context = _get_signature_context(sibling)
                    if signature_context[0] is not None:
                        return signature_context

        if curr.type in types:
            signature_context = _get_signature_context(curr)
            if signature_context[0] is not None:
                return signature_context

            name_node = _get_declaration_name(curr)
            return (
                _get_node_text(name_node) if name_node else None,
                curr.type,
                curr.start_point[0] + 1,
            )
        curr = curr.parent
    return None, None, None


def _calculate_complexity(node: Any) -> int:
    """Estimate cyclomatic complexity for a Dart AST node."""

    complexity_nodes = {
        "if_statement",
        "for_statement",
        "while_statement",
        "do_statement",
        "switch_statement",
        "switch_case",
        "if_element",
        "for_element",
        "conditional_expression",
        "binary_expression",
        "catch_clause",
    }
    count = 1

    def traverse(curr: Any) -> None:
        """Traverse a Dart AST subtree and update complexity state."""

        nonlocal count
        if curr.type in complexity_nodes:
            if curr.type == "binary_expression":
                op = curr.child_by_field_name("operator")
                if op and _get_node_text(op) in ("&&", "||"):
                    count += 1
            else:
                count += 1
        for child in curr.children:
            traverse(child)

    traverse(node)
    return count


def _find_functions(parser: Any, root_node: Any):
    """Find Dart function and method declarations in the parse tree."""

    functions = []
    seen_nodes = set()
    for node, capture_name in execute_query(
        parser.language, DART_QUERIES["functions"], root_node
    ):
        if capture_name != "function_node":
            continue

        node_id = (node.start_byte, node.end_byte)
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)

        name_node = node.child_by_field_name("name")
        if name_node is None and node.type == "mixin_declaration":
            name_node = next(
                (child for child in node.children if child.type == "identifier"),
                None,
            )
        if not name_node:
            continue

        params_node = node.child_by_field_name(
            "parameters"
        ) or node.child_by_field_name("formal_parameter_list")
        args = []
        if params_node:
            for child in params_node.children:
                if child.type == "formal_parameter":
                    param_name = _extract_param_name(child)
                    if param_name:
                        args.append(param_name)

        body_node = _find_function_body(node)
        context, context_type, _ = _get_parent_context(node)
        class_context = _find_class_context(node)

        func_data = {
            "name": _get_node_text(name_node),
            "line_number": node.start_point[0] + 1,
            "end_line": (body_node or node).end_point[0] + 1,
            "args": args,
            "cyclomatic_complexity": (
                _calculate_complexity(body_node) if body_node else 1
            ),
            "context": context,
            "context_type": context_type,
            "class_context": class_context,
            "lang": parser.language_name,
            "is_dependency": False,
        }
        if parser.index_source:
            func_data["source"] = _get_node_text(node) + (
                _get_node_text(body_node) if body_node else ""
            )

        functions.append(func_data)
    return functions


def _find_function_body(node: Any):
    """Return the sibling function body for one Dart signature node."""

    parent = node.parent
    if parent is None:
        return None

    found_signature = False
    for child in parent.children:
        if child == node:
            found_signature = True
            continue
        if not found_signature:
            continue
        if child.type == "function_body":
            return child
        if child.type in (
            "function_signature",
            "method_signature",
            "declaration",
            "class_definition",
        ):
            break
    return None


def _find_class_context(node: Any) -> str | None:
    """Return the nearest enclosing Dart class name."""

    curr = node.parent
    while curr:
        if curr.type == "class_definition":
            name_node = curr.child_by_field_name("name")
            return _get_node_text(name_node) if name_node else None
        curr = curr.parent
    return None


def _extract_param_name(param_node: Any) -> str | None:
    """Extract a Dart parameter name from a formal parameter node."""

    def find_id(node: Any) -> str | None:
        """Recursively locate the first identifier below a node."""

        if node.type == "identifier":
            return _get_node_text(node)
        for child in node.children:
            result = find_id(child)
            if result:
                return result
        return None

    return find_id(param_node)


def _find_classes(parser: Any, root_node: Any):
    """Find Dart class-like declarations."""

    classes = []
    for node, capture_name in execute_query(
        parser.language, DART_QUERIES["classes"], root_node
    ):
        if capture_name != "class":
            continue

        name_node = _get_declaration_name(node)
        if not name_node:
            continue

        bases = []
        for child in node.children:
            if child.type in ("superclass", "interfaces", "mixins"):
                for sub in child.children:
                    if sub.type in ("type_identifier", "type_not_void"):
                        bases.append(_get_node_text(sub))

        class_data = {
            "name": _get_node_text(name_node),
            "line_number": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "bases": bases,
            "lang": parser.language_name,
            "is_dependency": False,
        }
        if parser.index_source:
            class_data["source"] = _get_node_text(node)

        classes.append(class_data)
    return classes


def _find_imports(parser: Any, root_node: Any):
    """Find Dart import and export directives."""

    imports = []
    for node, capture_name in execute_query(
        parser.language, DART_QUERIES["imports"], root_node
    ):
        if capture_name != "import":
            continue

        uri_node = _find_uri_node(node)
        if uri_node is None:
            continue

        uri_text = _get_node_text(uri_node).strip("'\"")
        imports.append(
            {
                "name": uri_text,
                "full_import_name": uri_text,
                "line_number": node.start_point[0] + 1,
                "alias": _find_import_alias(node),
                "lang": parser.language_name,
                "is_dependency": False,
            }
        )
    return imports


def _find_uri_node(node: Any):
    """Locate the first URI node in one import subtree."""

    if node.type == "uri":
        return node
    for child in node.children:
        uri_node = _find_uri_node(child)
        if uri_node is not None:
            return uri_node
    return None


def _find_import_alias(node: Any) -> str | None:
    """Return the alias for one Dart import when present."""

    for child in node.children:
        if child.type != "import_specification":
            continue
        for sub in child.children:
            if sub.type != "prefix":
                continue
            alias_node = sub.child_by_field_name("identifier")
            if alias_node:
                return _get_node_text(alias_node)
    return None


def _find_variables(parser: Any, root_node: Any):
    """Find Dart variable declarations."""

    variables = []
    for node, capture_name in execute_query(
        parser.language, DART_QUERIES["variables"], root_node
    ):
        if capture_name != "name":
            continue
        context, _, _ = _get_parent_context(node)
        variables.append(
            {
                "name": _get_node_text(node),
                "line_number": node.start_point[0] + 1,
                "context": context,
                "lang": parser.language_name,
                "is_dependency": False,
            }
        )
    return variables


def pre_scan_dart(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Pre-scan Dart files to map top-level names to file paths."""

    name_to_files: dict[str, list[str]] = {}
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()
            tree = parser_wrapper.parser.parse(content.encode("utf8"))
            for node, _ in execute_query(
                parser_wrapper.language, PRESCAN_QUERY, tree.root_node
            ):
                name_to_files.setdefault(_get_node_text(node), []).append(
                    str(path.resolve())
                )
        except Exception as exc:
            warning_logger(f"Error pre-scanning Dart file {path}: {exc}")
    return name_to_files
