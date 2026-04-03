"""Support helpers for the handwritten C# parser."""

from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

CSHARP_QUERIES = {
    "functions": """
        (method_declaration
            name: (identifier) @name
            parameters: (parameter_list) @params
        ) @function_node

        (constructor_declaration
            name: (identifier) @name
            parameters: (parameter_list) @params
        ) @function_node

        (local_function_statement
            name: (identifier) @name
            parameters: (parameter_list) @params
        ) @function_node
    """,
    "classes": """
        (class_declaration 
            name: (identifier) @name
            (base_list)? @bases
        ) @class
    """,
    "interfaces": """
        (interface_declaration 
            name: (identifier) @name
            (base_list)? @bases
        ) @interface
    """,
    "structs": """
        (struct_declaration 
            name: (identifier) @name
            (base_list)? @bases
        ) @struct
    """,
    "enums": """
        (enum_declaration 
            name: (identifier) @name
        ) @enum
    """,
    "records": """
        (record_declaration 
            name: (identifier) @name
            (base_list)? @bases
        ) @record
    """,
    "properties": """
        (property_declaration
            name: (identifier) @name
        ) @property
    """,
    "imports": """
        (using_directive) @import
    """,
    "calls": """
        (invocation_expression
            function: [
                (identifier) @name
                (member_access_expression
                    name: (identifier) @name
                )
            ]
        )

        (object_creation_expression
            type: [
                (identifier) @name
                (qualified_name) @name
            ]
        )
    """,
}


def parse_csharp_file(
    parser: Any, path: Path, is_dependency: bool = False, index_source: bool = False
) -> dict[str, Any]:
    """Parse one C# file into the repository's normalized structure."""
    try:
        parser.index_source = index_source
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            source_code = handle.read()

        if not source_code.strip():
            warning_logger(f"Empty or whitespace-only file: {path}")
            return _empty_result(path, is_dependency)

        tree = parser.parser.parse(bytes(source_code, "utf8"))
        parsed_functions = []
        parsed_classes = []
        parsed_interfaces = []
        parsed_structs = []
        parsed_enums = []
        parsed_records = []
        parsed_properties = []
        parsed_imports = []
        parsed_calls = []

        for capture_name, query_str in CSHARP_QUERIES.items():
            captures = execute_query(parser.language, query_str, tree.root_node)
            if capture_name == "functions":
                parsed_functions = _parse_functions(
                    parser, captures, source_code, path, tree.root_node
                )
            elif capture_name == "classes":
                parsed_classes = _parse_type_declarations(
                    parser, captures, source_code, path, "Class"
                )
            elif capture_name == "interfaces":
                parsed_interfaces = _parse_type_declarations(
                    parser, captures, source_code, path, "Interface"
                )
            elif capture_name == "structs":
                parsed_structs = _parse_type_declarations(
                    parser, captures, source_code, path, "Struct"
                )
            elif capture_name == "enums":
                parsed_enums = _parse_type_declarations(
                    parser, captures, source_code, path, "Enum"
                )
            elif capture_name == "records":
                parsed_records = _parse_type_declarations(
                    parser, captures, source_code, path, "Record"
                )
            elif capture_name == "properties":
                parsed_properties = _parse_properties(
                    parser, captures, source_code, path, tree.root_node
                )
            elif capture_name == "imports":
                parsed_imports = _parse_imports(parser, captures, source_code)
            elif capture_name == "calls":
                parsed_calls = _parse_calls(parser, captures, source_code)

        return {
            "path": str(path),
            "functions": parsed_functions,
            "classes": parsed_classes,
            "interfaces": parsed_interfaces,
            "structs": parsed_structs,
            "enums": parsed_enums,
            "records": parsed_records,
            "properties": parsed_properties,
            "variables": [],
            "imports": parsed_imports,
            "function_calls": parsed_calls,
            "is_dependency": is_dependency,
            "lang": parser.language_name,
        }
    except Exception as exc:
        error_logger(f"Error parsing C# file {path}: {exc}")
        return _empty_result(path, is_dependency)


def _empty_result(path: Path, is_dependency: bool) -> dict[str, Any]:
    """Return the standard empty parse payload for C# files."""
    return {
        "path": str(path),
        "functions": [],
        "classes": [],
        "interfaces": [],
        "structs": [],
        "enums": [],
        "records": [],
        "properties": [],
        "variables": [],
        "imports": [],
        "function_calls": [],
        "is_dependency": is_dependency,
        "lang": "c_sharp",
    }


def _get_node_text(node: Any) -> str:
    """Decode source text from a tree-sitter node."""
    if not node:
        return ""
    return node.text.decode("utf-8")


def _get_parent_context(
    parser: Any,
    node: Any,
    types: tuple[str, ...] = (
        "class_declaration",
        "struct_declaration",
        "function_declaration",
        "method_declaration",
    ),
):
    """Return the nearest enclosing C# declaration for a node."""
    del parser
    curr = node.parent
    while curr:
        if curr.type in types:
            name_node = curr.child_by_field_name("name")
            return (
                _get_node_text(name_node) if name_node else None,
                curr.type,
                curr.start_point[0] + 1,
            )
        curr = curr.parent
    return None, None, None


def _parse_functions(
    parser: Any, captures: list, source_code: str, path: Path, root_node: Any
) -> list[dict[str, Any]]:
    """Parse C# function, constructor, and local function declarations."""
    del root_node
    functions = []
    for node, capture_name in captures:
        if capture_name != "function_node":
            continue
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            name_captures = [
                (n, cn) for n, cn in captures if cn == "name" and n.parent.id == node.id
            ]
            if not name_captures:
                continue

            name_node = name_captures[0][0]
            params_captures = [
                (n, cn)
                for n, cn in captures
                if cn == "params" and n.parent.id == node.id
            ]
            parameters = []
            if params_captures:
                parameters = _extract_parameters(parser, params_captures[0][0])

            attributes = []
            if node.parent and node.parent.type == "attribute_list":
                attributes.append(_get_node_text(node.parent))

            class_context = _find_containing_type(parser, node, source_code)
            func_data = {
                "name": _get_node_text(name_node),
                "args": parameters,
                "attributes": attributes,
                "line_number": start_line,
                "end_line": end_line,
                "path": str(path),
                "lang": parser.language_name,
            }
            if class_context:
                func_data["class_context"] = class_context
            if parser.index_source:
                func_data["source"] = _get_node_text(node)
            functions.append(func_data)
        except Exception as exc:
            error_logger(f"Error parsing function in {path}: {exc}")
    return functions


def _parse_type_declarations(
    parser: Any, captures: list, source_code: str, path: Path, type_label: str
) -> list[dict[str, Any]]:
    """Parse C# type declarations with inheritance information."""
    del source_code
    types = []
    capture_map = {
        "Class": "class",
        "Interface": "interface",
        "Struct": "struct",
        "Enum": "enum",
        "Record": "record",
    }
    expected_capture = capture_map.get(type_label, "class")

    for node, capture_name in captures:
        if capture_name != expected_capture:
            continue
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            name_captures = [
                (n, cn) for n, cn in captures if cn == "name" and n.parent.id == node.id
            ]
            if not name_captures:
                continue

            name_node = name_captures[0][0]
            bases = []
            bases_captures = [
                (n, cn)
                for n, cn in captures
                if cn == "bases" and n.parent.id == node.id
            ]
            if bases_captures:
                bases_text = (
                    _get_node_text(bases_captures[0][0]).strip().lstrip(":").strip()
                )
                if bases_text:
                    bases = [base.strip() for base in bases_text.split(",")]

            type_data = {
                "name": _get_node_text(name_node),
                "line_number": start_line,
                "end_line": end_line,
                "path": str(path),
                "lang": parser.language_name,
            }
            if bases:
                type_data["bases"] = bases
            if parser.index_source:
                type_data["source"] = _get_node_text(node)
            types.append(type_data)
        except Exception as exc:
            error_logger(f"Error parsing {type_label} in {path}: {exc}")
    return types


def _parse_imports(
    parser: Any, captures: list, source_code: str
) -> list[dict[str, Any]]:
    """Parse C# using directives."""
    del source_code
    imports = []
    for node, capture_name in captures:
        if capture_name != "import":
            continue
        try:
            import_text = _get_node_text(node)
            import_match = re.search(r"using\s+(?:static\s+)?([^;]+)", import_text)
            if not import_match:
                continue

            import_path = import_match.group(1).strip()
            alias = None
            if "=" in import_path:
                alias, import_path = [
                    part.strip() for part in import_path.split("=", 1)
                ]

            imports.append(
                {
                    "name": import_path,
                    "full_import_name": import_path,
                    "line_number": node.start_point[0] + 1,
                    "alias": alias,
                    "context": (None, None),
                    "lang": parser.language_name,
                    "is_dependency": False,
                }
            )
        except Exception as exc:
            error_logger(f"Error parsing import: {exc}")
    return imports


def _parse_calls(parser: Any, captures: list, source_code: str) -> list[dict[str, Any]]:
    """Parse C# invocation and object creation expressions."""
    del source_code
    calls = []
    seen_calls = set()
    for node, capture_name in captures:
        if capture_name != "name":
            continue
        try:
            call_name = _get_node_text(node)
            line_number = node.start_point[0] + 1
            call_key = f"{call_name}_{line_number}"
            if call_key in seen_calls:
                continue
            seen_calls.add(call_key)

            context_name, context_type, context_line = _get_parent_context(parser, node)
            class_context = (
                context_name if context_type and "class" in context_type else None
            )
            calls.append(
                {
                    "name": call_name,
                    "full_name": call_name,
                    "line_number": line_number,
                    "args": [],
                    "inferred_obj_type": None,
                    "context": (context_name, context_type, context_line),
                    "class_context": class_context,
                    "lang": parser.language_name,
                    "is_dependency": False,
                }
            )
        except Exception as exc:
            error_logger(f"Error parsing call: {exc}")
    return calls


def _extract_parameters(parser: Any, params_node: Any) -> list[str]:
    """Extract C# parameter names from a parameter node."""
    del parser
    params = []
    for child in params_node.children:
        if child.type == "parameter":
            name_node = child.child_by_field_name("name")
            if name_node:
                params.append(_get_node_text(name_node))
            else:
                for sub in child.children:
                    if sub.type == "identifier":
                        params.append(_get_node_text(sub))
                        break
    return params


def _find_containing_type(parser: Any, node: Any, source_code: str):
    """Return the enclosing type name for a node inside a C# type declaration."""
    del parser, source_code
    current = node.parent
    while current:
        if current.type in [
            "class_declaration",
            "struct_declaration",
            "interface_declaration",
            "record_declaration",
        ]:
            for child in current.children:
                if child.type == "identifier":
                    return _get_node_text(child)
        current = current.parent
    return None


def _parse_properties(
    parser: Any, captures: list, source_code: str, path: Path, root_node: Any
) -> list[dict[str, Any]]:
    """Parse C# property declarations."""
    del root_node
    properties = []
    for node, capture_name in captures:
        if capture_name != "property":
            continue
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            name_captures = [
                (n, cn) for n, cn in captures if cn == "name" and n.parent == node
            ]
            if not name_captures:
                continue

            name_node = name_captures[0][0]
            prop_name = _get_node_text(name_node)
            prop_type = None
            for child in node.children:
                if child.type in [
                    "predefined_type",
                    "identifier",
                    "generic_name",
                    "nullable_type",
                    "array_type",
                ]:
                    prop_type = _get_node_text(child)
                    break

            class_context = _find_containing_type(parser, node, source_code)
            prop_data = {
                "name": prop_name,
                "type": prop_type,
                "line_number": start_line,
                "end_line": end_line,
                "path": str(path),
                "lang": parser.language_name,
            }
            if class_context:
                prop_data["class_context"] = class_context
            if parser.index_source:
                prop_data["source"] = _get_node_text(node)
            properties.append(prop_data)
        except Exception as exc:
            error_logger(f"Error parsing property in {path}: {exc}")
    return properties
