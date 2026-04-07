"""Support helpers for the handwritten TypeScript parser."""

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import warning_logger
from platform_context_graph.utils.source_text import read_source_text
from platform_context_graph.utils.tree_sitter_manager import execute_query

TS_QUERIES = {
    "functions": """
        (function_declaration
            name: (identifier) @name
            parameters: (formal_parameters) @params
        ) @function_node
        (variable_declarator
            name: (identifier) @name
            value: (function_expression
                parameters: (formal_parameters) @params
            ) @function_node
        )
        (variable_declarator
            name: (identifier) @name
            value: (arrow_function
                parameters: (formal_parameters) @params
            ) @function_node
        )
        (variable_declarator
            name: (identifier) @name
            value: (arrow_function
                parameter: (identifier) @single_param
            ) @function_node
        )
        (method_definition
            name: (property_identifier) @name
            parameters: (formal_parameters) @params
        ) @function_node
        (assignment_expression
            left: (member_expression
                property: (property_identifier) @name
            )
            right: (function_expression
                parameters: (formal_parameters) @params
            ) @function_node
        )
        (assignment_expression
            left: (member_expression
                property: (property_identifier) @name
            )
            right: (arrow_function
                parameters: (formal_parameters) @params
            ) @function_node
        )
    """,
    "classes": """
        (class_declaration) @class
        (abstract_class_declaration) @class
        (class) @class
    """,
    "interfaces": """
        (interface_declaration
            name: (type_identifier) @name
        ) @interface_node
    """,
    "type_aliases": """
        (type_alias_declaration
            name: (type_identifier) @name
        ) @type_alias_node
    """,
    "imports": """
        (import_statement) @import
        (call_expression
            function: (identifier) @require_call (#eq? @require_call "require")
        ) @import
    """,
    "calls": """
        (call_expression function: (identifier) @name)
        (call_expression function: (member_expression property: (property_identifier) @name))
        (new_expression constructor: (identifier) @name)
        (new_expression constructor: (member_expression property: (property_identifier) @name))
    """,
    "variables": """
        (variable_declarator name: (identifier) @name)
    """,
    "variables_module": """
        (program
            (lexical_declaration
                (variable_declarator name: (identifier) @name)))
        (program
            (variable_declaration
                (variable_declarator name: (identifier) @name)))
        (export_statement
            declaration: (lexical_declaration
                (variable_declarator name: (identifier) @name)))
        (export_statement
            declaration: (variable_declaration
                (variable_declarator name: (identifier) @name)))
    """,
    "enums": """
        (enum_declaration
            name: (identifier) @name
        ) @enum_node
    """,
}


def is_typescript_file(path: Path) -> bool:
    """Return whether the path is a TypeScript source file.

    Args:
        path: Path to inspect.

    Returns:
        ``True`` when the path has a TypeScript extension.
    """
    return path.suffix in {".ts", ".tsx"}


def get_parent_context(
    node: Any,
    get_node_text: Any,
    types: tuple[str, ...] = (
        "function_declaration",
        "class_declaration",
        "method_definition",
        "function_expression",
        "arrow_function",
    ),
) -> tuple[str | None, str | None, int | None]:
    """Return the nearest enclosing TypeScript declaration for a node.

    Args:
        node: Tree-sitter node whose context is needed.
        get_node_text: Callable that decodes node text.
        types: Declaration node types that count as context boundaries.

    Returns:
        A tuple of declaration name, declaration type, and 1-based line number.
    """
    curr = node.parent
    while curr:
        if curr.type in types:
            name_node = curr.child_by_field_name("name")
            if not name_node and curr.type in ("function_expression", "arrow_function"):
                if curr.parent and curr.parent.type == "variable_declarator":
                    name_node = curr.parent.child_by_field_name("name")
                elif curr.parent and curr.parent.type == "assignment_expression":
                    name_node = curr.parent.child_by_field_name("left")
                elif curr.parent and curr.parent.type == "pair":
                    name_node = curr.parent.child_by_field_name("key")
            return (
                get_node_text(name_node) if name_node else None,
                curr.type,
                curr.start_point[0] + 1,
            )
        curr = curr.parent
    return None, None, None


def calculate_complexity(node: Any) -> int:
    """Estimate cyclomatic complexity for a TypeScript node.

    Args:
        node: Tree-sitter node representing a function body.

    Returns:
        Cyclomatic complexity estimate starting at 1.
    """
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
        "catch_clause",
    }
    count = 1

    def traverse(current: Any) -> None:
        """Traverse a TypeScript AST subtree and update complexity state."""
        nonlocal count
        if current.type in complexity_nodes:
            count += 1
        for child in current.children:
            traverse(child)

    traverse(node)
    return count


def extract_parameters(params_node: Any, get_node_text: Any) -> list[str]:
    """Extract parameter names from a TypeScript ``formal_parameters`` node.

    Args:
        params_node: Tree-sitter node for formal parameters.
        get_node_text: Callable that decodes node text.

    Returns:
        List of parameter names.
    """
    params: list[str] = []
    if params_node.type != "formal_parameters":
        return params

    for child in params_node.children:
        if child.type == "identifier":
            params.append(get_node_text(child))
        elif child.type == "required_parameter":
            pattern = child.child_by_field_name("pattern")
            if pattern:
                params.extend(_extract_pattern_parameters(pattern, get_node_text))
            else:
                for sub in child.children:
                    if sub.type in ("identifier", "object_pattern", "array_pattern"):
                        params.extend(_extract_pattern_parameters(sub, get_node_text))
                        break
        elif child.type == "optional_parameter":
            pattern = child.child_by_field_name("pattern")
            if pattern:
                params.extend(_extract_pattern_parameters(pattern, get_node_text))
        elif child.type == "assignment_pattern":
            left_child = child.child_by_field_name("left")
            if left_child:
                params.extend(_extract_pattern_parameters(left_child, get_node_text))
        elif child.type == "rest_pattern":
            argument = child.child_by_field_name("argument")
            if argument:
                params.extend(
                    _extract_pattern_parameters(
                        argument, get_node_text, include_rest_prefix=True
                    )
                )
    return list(dict.fromkeys(params))


def _extract_pattern_parameters(
    node: Any, get_node_text: Any, *, include_rest_prefix: bool = False
) -> list[str]:
    """Extract bound parameter names from one TypeScript pattern node."""

    if node.type in {"identifier", "shorthand_property_identifier_pattern"}:
        name = get_node_text(node)
        return [f"...{name}" if include_rest_prefix else name]
    if node.type in {"object_pattern", "array_pattern"}:
        params: list[str] = []
        for child in node.children:
            params.extend(_extract_pattern_parameters(child, get_node_text))
        return params
    if node.type in {"required_parameter", "optional_parameter"}:
        pattern = node.child_by_field_name("pattern")
        if pattern is not None:
            return _extract_pattern_parameters(
                pattern, get_node_text, include_rest_prefix=include_rest_prefix
            )
    if node.type == "assignment_pattern":
        left_child = node.child_by_field_name("left")
        if left_child is not None:
            return _extract_pattern_parameters(
                left_child, get_node_text, include_rest_prefix=include_rest_prefix
            )
    if node.type == "object_assignment_pattern":
        left_child = node.child_by_field_name("left")
        if left_child is not None:
            return _extract_pattern_parameters(
                left_child, get_node_text, include_rest_prefix=include_rest_prefix
            )
    if node.type == "pair_pattern":
        value_child = node.child_by_field_name("value")
        if value_child is not None:
            return _extract_pattern_parameters(
                value_child, get_node_text, include_rest_prefix=include_rest_prefix
            )
        key_child = node.child_by_field_name("key")
        if key_child is not None:
            return _extract_pattern_parameters(
                key_child, get_node_text, include_rest_prefix=include_rest_prefix
            )
    if node.type == "rest_pattern":
        argument = node.child_by_field_name("argument")
        if argument is not None:
            return _extract_pattern_parameters(
                argument, get_node_text, include_rest_prefix=True
            )
    return []


def is_valid_function_node(node: Any) -> bool:
    """Return whether a captured TypeScript function node is trustworthy.

    When `.tsx` files are parsed with the plain TypeScript grammar, tree-sitter
    can recover invalid JSX states as synthetic ``method_definition`` nodes.
    Those recovered nodes may carry a control-flow keyword like ``if`` as the
    "name" and a huge body fragment as the parameter list. We keep normal
    declarations, but reject recovered method definitions that sit on an error
    node boundary.

    Args:
        node: Captured function-like tree-sitter node.

    Returns:
        ``True`` when the node should be emitted as a function entity.
    """
    if node.type != "method_definition":
        return True
    parent = getattr(node, "parent", None)
    if parent is None:
        return False
    if parent.type == "class_body":
        return True
    if parent.type == "ERROR":
        return False
    if parent.type != "object":
        return True
    grandparent = getattr(parent, "parent", None)
    return grandparent is not None and grandparent.type in {
        "arguments",
        "assignment_expression",
        "pair",
        "return_statement",
        "variable_declarator",
    }


def pre_scan_typescript(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Build a name-to-file map for TypeScript declarations.

    Args:
        files: TypeScript files to scan.
        parser_wrapper: Wrapper that exposes tree-sitter language and parser objects.

    Returns:
        Mapping of discovered names to source file paths.
    """
    imports_map: dict[str, list[str]] = {}
    query_strings = [
        "(class_declaration) @class",
        "(function_declaration) @function",
        "(variable_declarator) @var_decl",
        "(method_definition) @method",
        "(interface_declaration) @interface",
        "(type_alias_declaration) @type_alias",
    ]

    for path in files:
        try:
            source_code = read_source_text(path)
            tree = parser_wrapper.parser.parse(bytes(source_code, "utf8"))

            for query_str in query_strings:
                try:
                    for node, capture_name in execute_query(
                        parser_wrapper.language,
                        query_str,
                        tree.root_node,
                    ):
                        name = _extract_prescan_name(node, capture_name)
                        if name:
                            file_path = str(path.resolve())
                            imports_map.setdefault(name, [])
                            if file_path not in imports_map[name]:
                                imports_map[name].append(file_path)
                except Exception as query_error:
                    warning_logger(
                        f"Query failed for pattern '{query_str}': {query_error}"
                    )
        except Exception as exc:
            warning_logger(f"Tree-sitter pre-scan failed for {path}: {exc}")

    return imports_map


def _extract_prescan_name(node: Any, capture_name: str) -> str | None:
    """Extract a declaration name for the TypeScript pre-scan map.

    Args:
        node: Captured tree-sitter node.
        capture_name: Query capture name.

    Returns:
        Declaration name when one can be determined.
    """
    if capture_name in {"class", "function", "method", "interface", "type_alias"}:
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8")
        return None
    if capture_name == "var_decl":
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        if (
            name_node
            and value_node
            and value_node.type in ("function", "arrow_function")
        ):
            return name_node.text.decode("utf-8")
    return None
