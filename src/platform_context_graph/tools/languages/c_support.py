"""Support helpers for the handwritten C parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

C_QUERIES = {
    "functions": """
        (function_definition
            declarator: (function_declarator
                declarator: (identifier) @name
            )
        ) @function_node

        (function_definition
            declarator: (function_declarator
                declarator: (pointer_declarator
                    declarator: (identifier) @name
                )
            )
        ) @function_node
    """,
    "structs": """
        (struct_specifier
            name: (type_identifier) @name
        ) @struct
    """,
    "unions": """
        (union_specifier
            name: (type_identifier) @name
        ) @union
    """,
    "enums": """
        (enum_specifier
            name: (type_identifier) @name
        ) @enum
    """,
    "typedefs": """
        (type_definition
            declarator: (type_identifier) @name
        ) @typedef
    """,
    "imports": """
        (preproc_include
            path: [
                (string_literal) @path
                (system_lib_string) @path
            ]
        ) @import
    """,
    "calls": """
        (call_expression
            function: (identifier) @name
        )
    """,
    "variables": """
        (declaration
            declarator: (init_declarator
                declarator: (identifier) @name
            )
        )

        (declaration
            declarator: (init_declarator
                declarator: (pointer_declarator
                    declarator: (identifier) @name
                )
            )
        )

        (declaration
            declarator: (identifier) @name
        )

        (declaration
            declarator: (pointer_declarator
                declarator: (identifier) @name
            )
        )
    """,
    "macros": """
        (preproc_def
            name: (identifier) @name
        ) @macro
    """,
}


def parse_c_file(
    parser: Any, path: Path, is_dependency: bool = False, index_source: bool = False
) -> dict[str, Any]:
    """Parse one C file into the repository's normalized structure."""
    parser.index_source = index_source
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        source_code = handle.read()

    tree = parser.parser.parse(bytes(source_code, "utf8"))
    root_node = tree.root_node

    return {
        "path": str(path),
        "functions": _find_functions(parser, root_node),
        "classes": _find_structs_unions_enums(parser, root_node),
        "variables": _find_variables(parser, root_node),
        "imports": _find_imports(parser, root_node),
        "function_calls": _find_calls(parser, root_node),
        "macros": _find_macros(parser, root_node),
        "is_dependency": is_dependency,
        "lang": parser.language_name,
    }


def _get_node_text(node: Any) -> str:
    """Decode source text from a tree-sitter node."""
    return node.text.decode("utf-8")


def _get_parent_context(
    parser: Any,
    node: Any,
    types: tuple[str, ...] = (
        "function_definition",
        "struct_specifier",
        "union_specifier",
        "enum_specifier",
    ),
) -> tuple[str | None, str | None, int | None]:
    """Return the nearest enclosing C declaration for a node."""
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
            else:
                name_node = curr.child_by_field_name("name")
                if name_node:
                    return (
                        _get_node_text(name_node),
                        curr.type,
                        name_node.start_point[0] + 1,
                    )
        curr = curr.parent
    return None, None, None


def _calculate_complexity(node: Any) -> int:
    """Estimate cyclomatic complexity for a C AST node."""
    complexity_nodes = {
        "if_statement",
        "for_statement",
        "while_statement",
        "do_statement",
        "switch_statement",
        "case_statement",
        "conditional_expression",
        "logical_expression",
        "binary_expression",
        "goto_statement",
    }
    count = 1

    def traverse(current: Any) -> None:
        """Traverse a C AST subtree and update complexity state."""
        nonlocal count
        if current.type in complexity_nodes:
            count += 1
        for child in current.children:
            traverse(child)

    traverse(node)
    return count


def _get_docstring(parser: Any, node: Any) -> str | None:
    """Extract comment text that documents a C declaration."""
    del parser
    if node.parent:
        for child in node.parent.children:
            if child.type == "comment" and child.start_point[0] < node.start_point[0]:
                return _get_node_text(child)
    return None


def _parse_function_args(parser: Any, params_node: Any) -> list[dict[str, Any]]:
    """Parse C function arguments from a parameter list node."""
    del parser
    args: list[dict[str, Any]] = []
    if not params_node:
        return args

    for param in params_node.named_children:
        if param.type != "parameter_declaration":
            continue

        arg_info: dict[str, Any] = {
            "name": "",
            "type": None,
            "is_pointer": False,
            "is_array": False,
        }

        declarator = param.child_by_field_name("declarator")
        if declarator:
            if declarator.type == "identifier":
                arg_info["name"] = _get_node_text(declarator)
            elif declarator.type == "pointer_declarator":
                arg_info["is_pointer"] = True
                inner_declarator = declarator.child_by_field_name("declarator")
                if inner_declarator and inner_declarator.type == "identifier":
                    arg_info["name"] = _get_node_text(inner_declarator)
            elif declarator.type == "array_declarator":
                arg_info["is_array"] = True
                inner_declarator = declarator.child_by_field_name("declarator")
                if inner_declarator and inner_declarator.type == "identifier":
                    arg_info["name"] = _get_node_text(inner_declarator)

        type_node = param.child_by_field_name("type")
        if type_node:
            arg_info["type"] = _get_node_text(type_node)

        if param.type == "variadic_parameter":
            arg_info["name"] = "..."
            arg_info["type"] = "variadic"

        args.append(arg_info)

    return args


def _find_functions(parser: Any, root_node: Any) -> list[dict[str, Any]]:
    """Find C function definitions."""
    functions: list[dict[str, Any]] = []
    for match in execute_query(parser.language, C_QUERIES["functions"], root_node):
        capture_name = match[1]
        node = match[0]
        if capture_name != "name":
            continue

        func_node = node.parent.parent.parent
        name = _get_node_text(node)
        params_node = None
        for child in func_node.children:
            if child.type == "function_declarator":
                params_node = child.child_by_field_name("parameters")

        args = _parse_function_args(parser, params_node) if params_node else []
        context, context_type, _ = _get_parent_context(parser, func_node)
        func_data = {
            "name": name,
            "line_number": node.start_point[0] + 1,
            "end_line": func_node.end_point[0] + 1,
            "args": [arg["name"] for arg in args if arg["name"]],
            "docstring": _get_docstring(parser, func_node),
            "cyclomatic_complexity": _calculate_complexity(func_node),
            "context": context,
            "context_type": context_type,
            "class_context": None,
            "decorators": [],
            "lang": parser.language_name,
            "is_dependency": False,
            "detailed_args": args,
        }
        if parser.index_source:
            func_data["source"] = _get_node_text(func_node)
        functions.append(func_data)
    return functions


def _find_structs_unions_enums(parser: Any, root_node: Any) -> list[dict[str, Any]]:
    """Find C structs, unions, and enums."""
    classes: list[dict[str, Any]] = []
    for capture_key, type_label in (
        ("structs", "struct"),
        ("unions", "union"),
        ("enums", "enum"),
    ):
        for match in execute_query(parser.language, C_QUERIES[capture_key], root_node):
            capture_name = match[1]
            node = match[0]
            if capture_name != "name":
                continue

            type_node = node.parent
            name = _get_node_text(node)
            context, _, _ = _get_parent_context(parser, type_node)
            type_data = {
                "name": name,
                "line_number": node.start_point[0] + 1,
                "end_line": type_node.end_point[0] + 1,
                "bases": [],
                "docstring": _get_docstring(parser, type_node),
                "context": context,
                "decorators": [],
                "lang": parser.language_name,
                "is_dependency": False,
                "type": type_label,
            }
            if parser.index_source:
                type_data["source"] = _get_node_text(type_node)
            classes.append(type_data)

    return classes


def _find_imports(parser: Any, root_node: Any) -> list[dict[str, Any]]:
    """Find C include directives."""
    imports: list[dict[str, Any]] = []
    for match in execute_query(parser.language, C_QUERIES["imports"], root_node):
        capture_name = match[1]
        node = match[0]
        if capture_name != "path":
            continue
        path = _get_node_text(node).strip('"<>')
        context, _, _ = _get_parent_context(parser, node)
        imports.append(
            {
                "name": path,
                "full_import_name": path,
                "line_number": node.start_point[0] + 1,
                "alias": None,
                "context": context,
                "lang": parser.language_name,
                "is_dependency": False,
            }
        )
    return imports


def _find_calls(parser: Any, root_node: Any) -> list[dict[str, Any]]:
    """Find C function calls."""
    calls: list[dict[str, Any]] = []
    for match in execute_query(parser.language, C_QUERIES["calls"], root_node):
        capture_name = match[1]
        node = match[0]
        if capture_name != "name":
            continue

        call_node = (
            node.parent if node.parent.type == "call_expression" else node.parent.parent
        )
        call_name = _get_node_text(node)
        args: list[str] = []
        args_node = call_node.child_by_field_name("arguments")
        if args_node:
            for child in args_node.children:
                if child.type not in ["(", ")", ","]:
                    args.append(_get_node_text(child))

        context_name, context_type, context_line = _get_parent_context(
            parser, call_node
        )
        calls.append(
            {
                "name": call_name,
                "full_name": call_name,
                "line_number": node.start_point[0] + 1,
                "args": args,
                "inferred_obj_type": None,
                "context": (context_name, context_type, context_line),
                "class_context": None,
                "lang": parser.language_name,
                "is_dependency": False,
            }
        )
    return calls


def _find_variables(parser: Any, root_node: Any) -> list[dict[str, Any]]:
    """Find C variable declarations."""
    variables: list[dict[str, Any]] = []
    for match in execute_query(parser.language, C_QUERIES["variables"], root_node):
        capture_name = match[1]
        node = match[0]
        if capture_name != "name":
            continue

        var_name = _get_node_text(node)
        decl_node = node.parent
        while decl_node and decl_node.type != "declaration":
            decl_node = decl_node.parent

        var_type = None
        value = None
        is_pointer = False
        is_array = False
        if decl_node:
            for child in decl_node.children:
                if child.type in [
                    "primitive_type",
                    "type_identifier",
                    "sized_type_specifier",
                ]:
                    var_type = _get_node_text(child)
                elif child.type == "init_declarator":
                    declarator = child.child_by_field_name("declarator")
                    if declarator:
                        if declarator.type == "pointer_declarator":
                            is_pointer = True
                        elif declarator.type == "array_declarator":
                            is_array = True
                    if child.child_by_field_name("value"):
                        value = _get_node_text(child.child_by_field_name("value"))

        context, _, _ = _get_parent_context(parser, node)
        class_context, _, _ = _get_parent_context(
            parser,
            node,
            types=("struct_specifier", "union_specifier", "enum_specifier"),
        )
        variables.append(
            {
                "name": var_name,
                "line_number": node.start_point[0] + 1,
                "value": value,
                "type": var_type,
                "context": context,
                "class_context": class_context,
                "lang": parser.language_name,
                "is_dependency": False,
                "is_pointer": is_pointer,
                "is_array": is_array,
            }
        )
    return variables


def _find_macros(parser: Any, root_node: Any) -> list[dict[str, Any]]:
    """Find C preprocessor macro definitions."""
    macros: list[dict[str, Any]] = []
    for match in execute_query(parser.language, C_QUERIES["macros"], root_node):
        capture_name = match[1]
        node = match[0]
        if capture_name != "name":
            continue

        macro_node = node.parent
        name = _get_node_text(node)
        value = None
        if macro_node.child_by_field_name("value"):
            value = _get_node_text(macro_node.child_by_field_name("value"))

        params = []
        if macro_node.child_by_field_name("parameters"):
            params_node = macro_node.child_by_field_name("parameters")
            for child in params_node.children:
                if child.type == "identifier":
                    params.append(_get_node_text(child))

        context, _, _ = _get_parent_context(parser, macro_node)
        macro_data = {
            "name": name,
            "line_number": node.start_point[0] + 1,
            "end_line": macro_node.end_point[0] + 1,
            "value": value,
            "params": params,
            "context": context,
            "lang": parser.language_name,
            "is_dependency": False,
        }
        if parser.index_source:
            macro_data["source"] = _get_node_text(macro_node)
        macros.append(macro_data)
    return macros
