"""Support helpers for the handwritten C++ parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

CPP_QUERIES: dict[str, str] = {}


def parse_cpp_file(
    parser: Any, path: Path, is_dependency: bool = False, index_source: bool = False
) -> dict[str, Any]:
    """Parse one C++ file into the repository's normalized structure."""
    parser.index_source = index_source
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        source_code = handle.read()

    tree = parser.parser.parse(bytes(source_code, "utf8"))
    root_node = tree.root_node

    functions = _find_functions(parser, root_node)
    functions.extend(_find_lambda_assignments(parser, root_node))

    return {
        "path": str(path),
        "functions": functions,
        "classes": _find_classes(parser, root_node),
        "structs": _find_structs(parser, root_node),
        "enums": _find_enums(parser, root_node),
        "unions": _find_unions(parser, root_node),
        "macros": _find_macros(parser, root_node),
        "variables": _find_variables(parser, root_node),
        "declarations": [],
        "imports": _find_imports(parser, root_node),
        "function_calls": _find_calls(parser, root_node),
        "is_dependency": is_dependency,
        "lang": parser.language_name,
    }


def _get_node_text(node: Any) -> str:
    """Decode source text from a tree-sitter node."""
    return node.text.decode("utf-8")


def _find_functions(parser: Any, root_node: Any):
    """Find C++ free functions."""
    functions = []
    for match in execute_query(parser.language, CPP_QUERIES["functions"], root_node):
        capture_name = match[1]
        node = match[0]
        if capture_name != "name":
            continue

        func_node = node.parent.parent
        if func_node.type != "function_definition":
            curr = node
            while curr and curr.type != "function_definition":
                curr = curr.parent
            func_node = curr
        if not func_node:
            continue

        name = _get_node_text(node)
        params = _extract_function_params(parser, func_node)
        func_data = {
            "name": name,
            "line_number": node.start_point[0] + 1,
            "end_line": func_node.end_point[0] + 1,
            "args": params,
        }
        if parser.index_source:
            func_data["source"] = _get_node_text(func_node)
        functions.append(func_data)
    return functions


def _extract_function_params(parser: Any, func_node: Any) -> list[str]:
    """Extract a C++ function's parameter list."""
    del parser
    params: list[str] = []
    declarator_node = func_node.child_by_field_name("declarator")
    if not declarator_node:
        return params

    parameters_node = declarator_node.child_by_field_name("parameters")
    if not parameters_node or parameters_node.type != "parameter_list":
        return params

    for param in parameters_node.children:
        if param.type != "parameter_declaration":
            continue

        param_decl = param.child_by_field_name("declarator")
        while param_decl and param_decl.type not in (
            "identifier",
            "field_identifier",
            "type_identifier",
        ):
            child = param_decl.child_by_field_name("declarator")
            if child:
                param_decl = child
            else:
                break

        name = _get_node_text(param_decl) if param_decl else ""
        param_type_node = param.child_by_field_name("type")
        type_str = _get_node_text(param_type_node) if param_type_node else ""
        if name:
            params.append(f"{type_str} {name}" if type_str else name)
    return params


def _find_classes(parser: Any, root_node: Any):
    """Find C++ class declarations."""
    classes = []
    for match in execute_query(parser.language, CPP_QUERIES["classes"], root_node):
        capture_name = match[1]
        node = match[0]
        if capture_name != "name":
            continue
        class_node = node.parent
        class_data = {
            "name": _get_node_text(node),
            "line_number": node.start_point[0] + 1,
            "end_line": class_node.end_point[0] + 1,
            "bases": [],
        }
        if parser.index_source:
            class_data["source"] = _get_node_text(class_node)
        classes.append(class_data)
    return classes


def _find_imports(parser: Any, root_node: Any):
    """Find C++ include directives."""
    imports = []
    for match in execute_query(parser.language, CPP_QUERIES["imports"], root_node):
        capture_name = match[1]
        node = match[0]
        if capture_name != "path":
            continue
        imports.append(
            {
                "name": _get_node_text(node).strip("<>"),
                "full_import_name": _get_node_text(node).strip("<>"),
                "line_number": node.start_point[0] + 1,
                "alias": None,
            }
        )
    return imports


def _find_enums(parser: Any, root_node: Any):
    """Find C++ enum declarations."""
    enums = []
    for node, capture_name in execute_query(
        parser.language, CPP_QUERIES["enums"], root_node
    ):
        if capture_name != "name":
            continue
        enum_node = node.parent
        enum_data = {
            "name": _get_node_text(node),
            "line_number": node.start_point[0] + 1,
            "end_line": enum_node.end_point[0] + 1,
        }
        if parser.index_source:
            enum_data["source"] = _get_node_text(enum_node)
        enums.append(enum_data)
    return enums


def _find_structs(parser: Any, root_node: Any):
    """Find C++ struct declarations."""
    structs = []
    for node, capture_name in execute_query(
        parser.language, CPP_QUERIES["structs"], root_node
    ):
        if capture_name != "name":
            continue
        struct_node = node.parent
        struct_data = {
            "name": _get_node_text(node),
            "line_number": node.start_point[0] + 1,
            "end_line": struct_node.end_point[0] + 1,
        }
        if parser.index_source:
            struct_data["source"] = _get_node_text(struct_node)
        structs.append(struct_data)
    return structs


def _find_unions(parser: Any, root_node: Any):
    """Find C++ union declarations."""
    unions = []
    for node, capture_name in execute_query(
        parser.language, CPP_QUERIES["unions"], root_node
    ):
        if capture_name != "name":
            continue
        union_node = node.parent
        union_data = {
            "name": _get_node_text(node),
            "line_number": node.start_point[0] + 1,
            "end_line": union_node.end_point[0] + 1,
        }
        if parser.index_source:
            union_data["source"] = _get_node_text(union_node)
        unions.append(union_data)
    return unions


def _find_macros(parser: Any, root_node: Any):
    """Find C++ macro definitions."""
    macros = []
    for match in execute_query(parser.language, CPP_QUERIES["macros"], root_node):
        capture_name = match[1]
        node = match[0]
        if capture_name != "name":
            continue
        macro_node = node.parent
        macro_data = {
            "name": _get_node_text(node),
            "line_number": node.start_point[0] + 1,
            "end_line": macro_node.end_point[0] + 1,
        }
        if parser.index_source:
            macro_data["source"] = _get_node_text(macro_node)
        macros.append(macro_data)
    return macros


def _find_lambda_assignments(parser: Any, root_node: Any):
    """Find lambda expressions assigned to variables in C++ files."""
    functions = []
    query_str = CPP_QUERIES.get("lambda_assignments")
    if not query_str:
        return functions

    for match in execute_query(parser.language, query_str, root_node):
        capture_name = match[1]
        node = match[0]
        if capture_name != "name":
            continue

        assignment_node = node.parent
        lambda_node = assignment_node.child_by_field_name("value")
        if lambda_node is None or lambda_node.type != "lambda_expression":
            continue

        params_node = lambda_node.child_by_field_name("parameters")
        context, context_type, _ = _get_parent_context(parser, assignment_node)
        class_context, _, _ = _get_parent_context(
            parser, assignment_node, types=("class_definition",)
        )
        func_data = {
            "name": _get_node_text(node),
            "line_number": node.start_point[0] + 1,
            "end_line": assignment_node.end_point[0] + 1,
            "args": (
                [
                    p
                    for p in [
                        _get_node_text(p)
                        for p in params_node.children
                        if p.type == "identifier"
                    ]
                    if p
                ]
                if params_node
                else []
            ),
            "docstring": None,
            "cyclomatic_complexity": 1,
            "context": context,
            "context_type": context_type,
            "class_context": class_context,
            "decorators": [],
            "lang": parser.language_name,
            "is_dependency": False,
        }
        if parser.index_source:
            func_data["source"] = _get_node_text(assignment_node)
        functions.append(func_data)
    return functions


def _find_variables(parser: Any, root_node: Any):
    """Find C++ variable declarations."""
    variables = []
    for match in execute_query(parser.language, CPP_QUERIES["variables"], root_node):
        capture_name = match[1]
        node = match[0]
        if capture_name != "name":
            continue

        assignment_node = node.parent
        right_node = assignment_node.child_by_field_name("value")
        if right_node and right_node.type == "lambda_expression":
            continue

        context, _, _ = _get_parent_context(parser, node)
        class_context, _, _ = _get_parent_context(
            parser, node, types=("class_definition",)
        )
        variables.append(
            {
                "name": _get_node_text(node),
                "line_number": node.start_point[0] + 1,
                "value": _get_node_text(right_node) if right_node else None,
                "type": (
                    _get_node_text(assignment_node.child_by_field_name("type"))
                    if assignment_node.child_by_field_name("type")
                    else None
                ),
                "context": context,
                "class_context": class_context,
                "lang": parser.language_name,
                "is_dependency": False,
            }
        )
    return variables


def _get_parent_context(
    parser: Any, node: Any, types=("function_definition", "class_definition")
):
    """Return the nearest enclosing C++ declaration for a node."""
    del parser
    curr = node.parent
    while curr:
        if curr.type in types:
            if curr.type == "function_definition":
                decl = curr.child_by_field_name("declarator")
                while decl:
                    if decl.type == "identifier":
                        return (
                            _get_node_text(decl),
                            curr.type,
                            decl.start_point[0] + 1,
                        )
                    child = decl.child_by_field_name("declarator")
                    if child:
                        decl = child
                    else:
                        break
                return None, curr.type, curr.start_point[0] + 1
            name_node = curr.child_by_field_name("name")
            return (
                _get_node_text(name_node) if name_node else None,
                curr.type,
                curr.start_point[0] + 1,
            )
        curr = curr.parent
    return None, None, None


def _find_calls(parser: Any, root_node: Any):
    """Find C++ call expressions."""
    calls = []
    for node, capture_name in execute_query(
        parser.language, CPP_QUERIES["calls"], root_node
    ):
        if capture_name != "function_name":
            continue

        func_name = _get_node_text(node)
        func_node = node.parent.parent
        full_name = _get_full_name(parser, func_node) or func_name

        return_type_node = None
        for captured_node, captured_name in execute_query(
            parser.language, CPP_QUERIES["calls"], func_node
        ):
            if captured_name == "return_type":
                return_type_node = captured_node
                break
        return_type = _get_node_text(return_type_node) if return_type_node else None

        args = []
        parameters_node = func_node.child_by_field_name("declarator")
        if parameters_node:
            param_list_node = parameters_node.child_by_field_name("parameters")
            if param_list_node:
                for param in param_list_node.children:
                    if param.type == "parameter_declaration":
                        type_node = param.child_by_field_name("type")
                        name_node = param.child_by_field_name("declarator")
                        args.append(
                            {
                                "type": (
                                    _get_node_text(type_node) if type_node else None
                                ),
                                "name": (
                                    _get_node_text(name_node) if name_node else None
                                ),
                            }
                        )

        context_name, context_type, context_line = _get_parent_context(parser, node)
        class_context, _, _ = _get_parent_context(
            parser, node, types=("class_definition",)
        )
        calls.append(
            {
                "name": func_name,
                "full_name": full_name,
                "return_type": return_type,
                "line_number": node.start_point[0] + 1,
                "args": args,
                "inferred_obj_type": None,
                "context": (context_name, context_type, context_line),
                "class_context": class_context,
                "lang": parser.language_name,
                "is_dependency": False,
            }
        )
    return calls


def _get_full_name(parser: Any, node: Any):
    """Build a qualified C++ symbol name."""
    del parser
    name_parts = []
    curr = node
    while curr:
        if curr.type in ("function_definition", "function_declarator"):
            id_node = curr.child_by_field_name("declarator")
            if id_node and id_node.type == "identifier":
                name_parts.insert(0, id_node.text.decode("utf8"))
        elif curr.type == "class_specifier":
            name_node = curr.child_by_field_name("name")
            if name_node:
                name_parts.insert(0, name_node.text.decode("utf8"))
        elif curr.type == "namespace_definition":
            name_node = curr.child_by_field_name("name")
            if name_node:
                name_parts.insert(0, name_node.text.decode("utf8"))
        curr = curr.parent
    return "::".join(name_parts) if name_parts else None
