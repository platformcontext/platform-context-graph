"""Import parsing helpers for the handwritten TypeScript parser."""

from __future__ import annotations

from typing import Any

from platform_context_graph.utils.tree_sitter_manager import execute_query

from .typescript_support import TS_QUERIES


def find_imports(
    language: Any,
    root_node: Any,
    *,
    get_node_text: Any,
    language_name: str,
) -> list[dict[str, Any]]:
    """Parse TypeScript ES module and CommonJS imports."""

    imports: list[dict[str, Any]] = []
    for node, capture_name in execute_query(language, TS_QUERIES["imports"], root_node):
        if capture_name != "import":
            continue
        line_number = node.start_point[0] + 1
        if node.type == "import_statement":
            imports.extend(
                _parse_es_import(
                    node,
                    line_number,
                    get_node_text=get_node_text,
                    language_name=language_name,
                )
            )
        elif node.type == "call_expression":
            import_data = _parse_require_import(
                node,
                line_number,
                get_node_text=get_node_text,
                language_name=language_name,
            )
            if import_data is not None:
                imports.append(import_data)
    return imports


def _parse_es_import(
    node: Any,
    line_number: int,
    *,
    get_node_text: Any,
    language_name: str,
) -> list[dict[str, Any]]:
    """Parse a TypeScript ES module import statement."""

    source = get_node_text(node.child_by_field_name("source")).strip("'\"")
    import_clause = node.child_by_field_name("import") or next(
        (child for child in node.children if child.is_named and child.type != "string"),
        None,
    )
    if not import_clause:
        return [
            {
                "name": source,
                "source": source,
                "alias": None,
                "line_number": line_number,
                "lang": language_name,
            }
        ]
    clause_nodes = [import_clause]
    if import_clause.type == "import_clause":
        clause_nodes = [child for child in import_clause.children if child.is_named]
    parsed_imports: list[dict[str, Any]] = []
    for clause_node in clause_nodes:
        if clause_node.type == "identifier":
            parsed_imports.append(
                {
                    "name": "default",
                    "source": source,
                    "alias": get_node_text(clause_node),
                    "line_number": line_number,
                    "lang": language_name,
                }
            )
            continue
        if clause_node.type == "namespace_import":
            alias_node = clause_node.child_by_field_name("alias") or next(
                (child for child in clause_node.children if child.is_named),
                None,
            )
            if alias_node:
                parsed_imports.append(
                    {
                        "name": "*",
                        "source": source,
                        "alias": get_node_text(alias_node),
                        "line_number": line_number,
                        "lang": language_name,
                    }
                )
            continue
        if clause_node.type != "named_imports":
            continue
        for specifier in clause_node.children:
            if specifier.type != "import_specifier":
                continue
            name_node = specifier.child_by_field_name("name")
            alias_node = specifier.child_by_field_name("alias")
            if name_node:
                parsed_imports.append(
                    {
                        "name": get_node_text(name_node),
                        "source": source,
                        "alias": get_node_text(alias_node) if alias_node else None,
                        "line_number": line_number,
                        "lang": language_name,
                    }
                )
    return parsed_imports


def _parse_require_import(
    node: Any,
    line_number: int,
    *,
    get_node_text: Any,
    language_name: str,
) -> dict[str, Any] | None:
    """Parse a TypeScript ``require()`` import expression."""

    args = node.child_by_field_name("arguments")
    if not args or args.named_child_count == 0:
        return None
    source_node = args.named_child(0)
    if not source_node or source_node.type != "string":
        return None
    source = get_node_text(source_node).strip("'\"")
    alias = None
    if node.parent.type == "variable_declarator":
        alias_node = node.parent.child_by_field_name("name")
        if alias_node:
            alias = get_node_text(alias_node)
    return {
        "name": source,
        "source": source,
        "alias": alias,
        "line_number": line_number,
        "lang": language_name,
    }
