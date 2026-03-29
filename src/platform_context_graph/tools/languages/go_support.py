"""Support helpers for the handwritten Go parser."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import debug_log, warning_logger
from platform_context_graph.utils.source_text import read_source_text
from platform_context_graph.utils.tree_sitter_manager import execute_query

GO_QUERIES = {
    "functions": """
        (function_declaration
            name: (identifier) @name
            parameters: (parameter_list) @params
        ) @function_node

        (method_declaration
            receiver: (parameter_list) @receiver
            name: (field_identifier) @name
            parameters: (parameter_list) @params
        ) @function_node
    """,
    "structs": """
        (type_declaration
            (type_spec
                name: (type_identifier) @name
                type: (struct_type) @struct_body
            )
        ) @struct_node
    """,
    "interfaces": """
        (type_declaration
            (type_spec
                name: (type_identifier) @name
                type: (interface_type) @interface_body
            )
        ) @interface_node
    """,
    "imports": """
        (import_spec
            path: (interpreted_string_literal) @path
        ) @import

        (import_spec
            name: (package_identifier) @alias
            path: (interpreted_string_literal) @path
        ) @import_alias
    """,
    "calls": """
        (call_expression
            function: (identifier) @name
        )
        (call_expression
            function: (selector_expression
                field: (field_identifier) @name
            )
        )
    """,
    "variables": """
        (var_declaration
            (var_spec
                name: (identifier) @name
            )
        )
        (short_var_declaration
            left: (expression_list
                (identifier) @name
            )
        )
        (const_declaration
            (const_spec
                name: (identifier) @name
            )
        )
    """,
    "variables_module": """
        (source_file (var_declaration (var_spec name: (identifier) @name)))
        (source_file (const_declaration (const_spec name: (identifier) @name)))
    """,
}


def parse_go_file(
    parser: Any, path: Path, is_dependency: bool = False, index_source: bool = False
) -> dict[str, Any]:
    """Parse one Go file into the repository's normalized structure."""
    parser.index_source = index_source
    source_code = read_source_text(path)

    tree = parser.parser.parse(bytes(source_code, "utf8"))
    root_node = tree.root_node

    return {
        "path": str(path),
        "functions": _find_functions(parser, root_node),
        "classes": _find_structs(parser, root_node),
        "interfaces": _find_interfaces(parser, root_node),
        "variables": _find_variables(parser, root_node),
        "imports": _find_imports(parser, root_node),
        "function_calls": _find_calls(parser, root_node),
        "is_dependency": is_dependency,
        "lang": parser.language_name,
    }


def _get_node_text(node: Any) -> str:
    """Decode source text from a tree-sitter node."""
    return node.text.decode("utf-8")


def _get_parent_context(
    parser: Any,
    node: Any,
    types=("function_declaration", "method_declaration", "type_declaration"),
):
    """Return the nearest enclosing declaration for a Go node."""
    del parser
    curr = node.parent
    while curr:
        if curr.type in types:
            if curr.type == "type_declaration":
                type_spec = curr.child_by_field_name("type_spec")
                if type_spec:
                    name_node = type_spec.child_by_field_name("name")
                    return (
                        _get_node_text(name_node) if name_node else None,
                        curr.type,
                        curr.start_point[0] + 1,
                    )
            else:
                name_node = curr.child_by_field_name("name")
                return (
                    _get_node_text(name_node) if name_node else None,
                    curr.type,
                    curr.start_point[0] + 1,
                )
        curr = curr.parent
    return None, None, None


def _calculate_complexity(node: Any) -> int:
    """Estimate cyclomatic complexity for a Go AST node."""
    complexity_nodes = {
        "if_statement",
        "for_statement",
        "switch_statement",
        "case_clause",
        "expression_switch_statement",
        "type_switch_statement",
        "binary_expression",
        "call_expression",
    }
    count = 1

    def traverse(current: Any) -> None:
        """Traverse a Go AST subtree and update complexity state."""
        nonlocal count
        if current.type in complexity_nodes:
            count += 1
        for child in current.children:
            traverse(child)

    traverse(node)
    return count


def _get_docstring(parser: Any, func_node: Any):
    """Extract a Go doc comment preceding a function declaration."""
    del parser
    prev_sibling = func_node.prev_sibling
    while prev_sibling and prev_sibling.type in ("comment", "\n", " "):
        if prev_sibling.type == "comment":
            comment_text = _get_node_text(prev_sibling)
            if comment_text.startswith("//"):
                return comment_text.strip()
        prev_sibling = prev_sibling.prev_sibling
    return None


def _find_functions(parser: Any, root_node: Any):
    """Find Go functions and methods."""
    functions = []
    captures_by_function = {}

    for node, capture_name in execute_query(
        parser.language, GO_QUERIES["functions"], root_node
    ):
        if capture_name == "function_node":
            func_id = node.id
            captures_by_function.setdefault(
                func_id,
                {"node": node, "name": None, "params": None, "receiver": None},
            )
        elif capture_name == "name":
            func_node = _find_function_node_for_name(node)
            if func_node:
                func_id = func_node.id
                captures_by_function.setdefault(
                    func_id,
                    {"node": func_node, "name": None, "params": None, "receiver": None},
                )
                captures_by_function[func_id]["name"] = _get_node_text(node)
        elif capture_name == "params":
            func_node = _find_function_node_for_params(node)
            if func_node:
                func_id = func_node.id
                captures_by_function.setdefault(
                    func_id,
                    {"node": func_node, "name": None, "params": None, "receiver": None},
                )
                captures_by_function[func_id]["params"] = node
        elif capture_name == "receiver":
            func_node = node.parent
            if func_node and func_node.type == "method_declaration":
                func_id = func_node.id
                captures_by_function.setdefault(
                    func_id,
                    {"node": func_node, "name": None, "params": None, "receiver": None},
                )
                captures_by_function[func_id]["receiver"] = node

    for func_id, data in captures_by_function.items():
        if not data["name"]:
            continue

        func_node = data["node"]
        args = _extract_parameters(parser, data["params"]) if data["params"] else []
        receiver_type = (
            _extract_receiver(parser, data["receiver"]) if data["receiver"] else None
        )
        context, context_type, _ = _get_parent_context(parser, func_node)
        class_context = receiver_type or (
            context if context_type == "type_declaration" else None
        )
        docstring = _get_docstring(parser, func_node)

        func_data = {
            "name": data["name"],
            "line_number": func_node.start_point[0] + 1,
            "end_line": func_node.end_point[0] + 1,
            "args": args,
            "class_context": class_context,
            "decorators": [],
            "lang": parser.language_name,
            "is_dependency": False,
        }
        if parser.index_source:
            func_data["source"] = _get_node_text(func_node)
            func_data["docstring"] = docstring
        functions.append(func_data)

    return functions


def _find_function_node_for_name(name_node: Any):
    """Return the Go function or method node containing a name capture."""
    current = name_node.parent
    while current:
        if current.type in ("function_declaration", "method_declaration"):
            return current
        current = current.parent
    return None


def _find_function_node_for_params(params_node: Any):
    """Return the Go function or method node containing a parameter capture."""
    current = params_node.parent
    while current:
        if current.type in ("function_declaration", "method_declaration"):
            return current
        current = current.parent
    return None


def _extract_parameters(parser: Any, params_node: Any):
    """Extract Go parameter names from a parameter list node."""
    del parser
    params = []
    if params_node.type == "parameter_list":
        for child in params_node.children:
            if child.type == "parameter_declaration":
                type_node = child.child_by_field_name("type")
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        if grandchild.id != (type_node.id if type_node else None):
                            params.append(_get_node_text(grandchild))
            elif child.type == "variadic_parameter_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    params.append(f"...{_get_node_text(name_node)}")
    return params


def _extract_receiver(parser: Any, receiver_node: Any):
    """Extract the Go receiver type name."""
    del parser
    if receiver_node.type == "parameter_list" and receiver_node.named_child_count > 0:
        param = receiver_node.named_child(0)
        type_node = param.child_by_field_name("type")
        if type_node:
            return _get_node_text(type_node).strip("*")
    return None


def _find_structs(parser: Any, root_node: Any):
    """Find Go struct declarations."""
    structs = []
    for node, capture_name in execute_query(
        parser.language, GO_QUERIES["structs"], root_node
    ):
        if capture_name != "name":
            continue
        struct_node = _find_type_declaration_for_name(node)
        if not struct_node:
            continue
        class_data = {
            "name": _get_node_text(node),
            "line_number": struct_node.start_point[0] + 1,
            "end_line": struct_node.end_point[0] + 1,
            "bases": [],
            "decorators": [],
            "lang": parser.language_name,
            "is_dependency": False,
        }
        if parser.index_source:
            class_data["source"] = _get_node_text(struct_node)
            class_data["docstring"] = _get_docstring(parser, struct_node)
        structs.append(class_data)
    return structs


def _find_interfaces(parser: Any, root_node: Any):
    """Find Go interface declarations."""
    interfaces = []
    for node, capture_name in execute_query(
        parser.language, GO_QUERIES["interfaces"], root_node
    ):
        if capture_name != "name":
            continue
        interface_node = _find_type_declaration_for_name(node)
        if not interface_node:
            continue
        class_data = {
            "name": _get_node_text(node),
            "line_number": interface_node.start_point[0] + 1,
            "end_line": interface_node.end_point[0] + 1,
            "bases": [],
            "decorators": [],
            "lang": parser.language_name,
            "is_dependency": False,
        }
        if parser.index_source:
            class_data["source"] = _get_node_text(interface_node)
            class_data["docstring"] = _get_docstring(parser, interface_node)
        interfaces.append(class_data)
    return interfaces


def _find_type_declaration_for_name(name_node: Any):
    """Return the enclosing Go type declaration for a captured name."""
    current = name_node.parent
    while current:
        if current.type == "type_declaration":
            return current
        current = current.parent
    return None


def _find_imports(parser: Any, root_node: Any):
    """Find Go import declarations."""
    imports = []
    for node, capture_name in execute_query(
        parser.language, GO_QUERIES["imports"], root_node
    ):
        line_number = node.start_point[0] + 1
        if capture_name != "path":
            continue

        path_text = _get_node_text(node).strip('"')
        package_name = path_text.split("/")[-1]
        alias = None
        import_spec = node.parent
        if import_spec and import_spec.type == "import_spec":
            alias_node = import_spec.child_by_field_name("name")
            if alias_node:
                alias = _get_node_text(alias_node)

        imports.append(
            {
                "name": package_name,
                "source": path_text,
                "alias": alias,
                "line_number": line_number,
                "lang": parser.language_name,
            }
        )
    return imports


def _find_calls(parser: Any, root_node: Any):
    """Find Go function calls."""
    calls = []
    seen_calls = set()
    for node, capture_name in execute_query(
        parser.language, GO_QUERIES["calls"], root_node
    ):
        if capture_name != "name":
            continue

        call_node = node.parent
        while call_node and call_node.type != "call_expression":
            call_node = call_node.parent
        if not call_node:
            continue

        name = _get_node_text(node)
        line_number = node.start_point[0] + 1
        call_key = f"{name}_{line_number}"
        if call_key in seen_calls:
            continue
        seen_calls.add(call_key)

        function_node = call_node.child_by_field_name("function")
        full_name = _get_node_text(function_node) if function_node else name
        context_name, context_type, context_line = _get_parent_context(parser, node)
        calls.append(
            {
                "name": name,
                "full_name": full_name,
                "line_number": line_number,
                "args": [],
                "inferred_obj_type": None,
                "context": (context_name, context_type, context_line),
                "class_context": None,
                "lang": parser.language_name,
                "is_dependency": False,
            }
        )
    return calls


def _find_variables(parser: Any, root_node: Any):
    """Find Go variable declarations, scope-filtered by PCG_VARIABLE_SCOPE."""
    scope = os.environ.get("PCG_VARIABLE_SCOPE", "").strip().lower()
    query_key = "variables" if scope == "all" else "variables_module"
    variables = []
    for node, capture_name in execute_query(
        parser.language, GO_QUERIES[query_key], root_node
    ):
        if capture_name != "name":
            continue
        variables.append(
            {
                "name": _get_node_text(node),
                "line_number": node.start_point[0] + 1,
                "value": None,
                "type": None,
                "context": None,
                "class_context": None,
                "lang": parser.language_name,
                "is_dependency": False,
            }
        )
    return variables


def pre_scan_go(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Pre-scan Go files to map top-level names to file paths."""
    imports_map: dict[str, list[str]] = {}
    query_str = """
        (function_declaration name: (identifier) @name)
        (method_declaration name: (field_identifier) @name)
        (type_declaration (type_spec name: (type_identifier) @name))
    """

    for path in files:
        try:
            source_code = read_source_text(path)
            tree = parser_wrapper.parser.parse(bytes(source_code, "utf8"))

            for capture, _ in execute_query(
                parser_wrapper.language, query_str, tree.root_node
            ):
                name = capture.text.decode("utf-8")
                imports_map.setdefault(name, []).append(str(path.resolve()))
        except Exception as exc:
            warning_logger(f"Tree-sitter pre-scan failed for {path}: {exc}")

    return imports_map
