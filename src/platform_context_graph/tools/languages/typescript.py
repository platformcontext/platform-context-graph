"""Compatibility facade for the handwritten TypeScript parser."""

from pathlib import Path
from typing import Any

from platform_context_graph.utils.source_text import read_source_text
from platform_context_graph.utils.tree_sitter_manager import execute_query

from .typescript_support import (
    TS_QUERIES,
    calculate_complexity,
    extract_parameters,
    get_parent_context,
    is_typescript_file,
    pre_scan_typescript,
)


class TypescriptTreeSitterParser:
    """Parse TypeScript source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Store the generic parser wrapper used for parsing.

        Args:
            generic_parser_wrapper: Wrapper providing language and parser objects.
        """
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = generic_parser_wrapper.language_name
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def _get_node_text(self, node: Any) -> str:
        """Decode a tree-sitter node to UTF-8 text.

        Args:
            node: Tree-sitter node to decode.

        Returns:
            Decoded node text.
        """
        return node.text.decode("utf-8")

    def _get_parent_context(
        self,
        node: Any,
        types: tuple[str, ...] = (
            "function_declaration",
            "class_declaration",
            "method_definition",
            "function_expression",
            "arrow_function",
        ),
    ) -> tuple[str | None, str | None, int | None]:
        """Return the nearest enclosing TypeScript declaration for a node."""
        return get_parent_context(node, self._get_node_text, types)

    def parse(
        self,
        path: Path,
        is_dependency: bool = False,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Parse a TypeScript file into the standard graph-friendly structure.

        Args:
            path: Source file path.
            is_dependency: Whether the file belongs to dependency code.
            index_source: Whether parsed nodes should include raw source text.

        Returns:
            Parsed functions, classes, interfaces, imports, calls, and variables.
        """
        self.index_source = index_source
        source_code = read_source_text(path)
        tree = self.parser.parse(bytes(source_code, "utf8"))
        root_node = tree.root_node

        return {
            "path": str(path),
            "functions": self._find_functions(root_node),
            "classes": self._find_classes(root_node),
            "interfaces": self._find_interfaces(root_node),
            "type_aliases": self._find_type_aliases(root_node),
            "enums": self._find_enums(root_node),
            "variables": self._find_variables(root_node),
            "imports": self._find_imports(root_node),
            "function_calls": self._find_calls(root_node),
            "is_dependency": is_dependency,
            "lang": self.language_name,
        }

    def _find_functions(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse TypeScript function-like declarations."""
        functions: list[dict[str, Any]] = []
        captures_by_function: dict[tuple[int, int, str], dict[str, Any]] = {}

        for node, capture_name in execute_query(
            self.language, TS_QUERIES["functions"], root_node
        ):
            function_node = self._resolve_function_capture(node, capture_name)
            if function_node is None:
                continue
            key = (function_node.start_byte, function_node.end_byte, function_node.type)
            bucket = captures_by_function.setdefault(
                key,
                {
                    "node": function_node,
                    "name": None,
                    "params": None,
                    "single_param": None,
                },
            )
            if capture_name == "name":
                bucket["name"] = self._get_node_text(node)
            elif capture_name == "params":
                bucket["params"] = node
            elif capture_name == "single_param":
                bucket["single_param"] = node

        for data in captures_by_function.values():
            func_node = data["node"]
            name = data["name"]
            if not name and func_node.type == "method_definition":
                name_node = func_node.child_by_field_name("name")
                if name_node:
                    name = self._get_node_text(name_node)
            if not name:
                continue

            args = []
            if data["params"] is not None:
                args = extract_parameters(data["params"], self._get_node_text)
            elif data["single_param"] is not None:
                args = [self._get_node_text(data["single_param"])]

            context, context_type, _ = self._get_parent_context(func_node)
            function_data = {
                "name": name,
                "line_number": func_node.start_point[0] + 1,
                "end_line": func_node.end_point[0] + 1,
                "args": args,
                "cyclomatic_complexity": calculate_complexity(func_node),
                "context": context,
                "context_type": context_type,
                "class_context": (
                    context if context_type == "class_declaration" else None
                ),
                "decorators": [],
                "lang": self.language_name,
                "is_dependency": False,
            }
            if self.index_source:
                function_data["source"] = self._get_node_text(func_node)
                function_data["docstring"] = None
            functions.append(function_data)

        return functions

    def _resolve_function_capture(self, node: Any, capture_name: str) -> Any | None:
        """Resolve a TypeScript query capture to its owning function node."""
        if capture_name == "function_node":
            return node
        current = node.parent
        while current:
            if current.type in (
                "function_declaration",
                "function",
                "arrow_function",
                "method_definition",
            ):
                return current
            if capture_name == "name" and current.type in (
                "variable_declarator",
                "assignment_expression",
            ):
                for child in current.children:
                    if child.type in ("function", "arrow_function"):
                        return child
            current = current.parent
        return None

    def _find_classes(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse TypeScript class declarations."""
        classes: list[dict[str, Any]] = []
        for class_node, capture_name in execute_query(
            self.language, TS_QUERIES["classes"], root_node
        ):
            if capture_name != "class":
                continue
            name_node = class_node.child_by_field_name("name")
            if not name_node:
                continue
            bases = self._extract_heritage_bases(class_node)
            class_data = {
                "name": self._get_node_text(name_node),
                "line_number": class_node.start_point[0] + 1,
                "end_line": class_node.end_point[0] + 1,
                "bases": bases,
                "context": None,
                "decorators": [],
                "lang": self.language_name,
                "is_dependency": False,
            }
            if self.index_source:
                class_data["source"] = self._get_node_text(class_node)
                class_data["docstring"] = None
            classes.append(class_data)
        return classes

    def _extract_heritage_bases(self, class_node: Any) -> list[str]:
        """Extract base types from a class heritage clause."""
        bases: list[str] = []
        heritage_node = next(
            (child for child in class_node.children if child.type == "class_heritage"),
            None,
        )
        if heritage_node is None:
            return bases
        for child in heritage_node.children:
            if child.type in ("extends_clause", "implements_clause"):
                for sub in child.children:
                    if sub.type in (
                        "identifier",
                        "type_identifier",
                        "member_expression",
                    ):
                        bases.append(self._get_node_text(sub))
        return bases

    def _find_interfaces(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse TypeScript interface declarations."""
        interfaces: list[dict[str, Any]] = []
        for node, capture_name in execute_query(
            self.language, TS_QUERIES["interfaces"], root_node
        ):
            if capture_name != "interface_node":
                continue
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue
            interface_data = {
                "name": self._get_node_text(name_node),
                "line_number": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
            }
            if self.index_source:
                interface_data["source"] = self._get_node_text(node)
            interfaces.append(interface_data)
        return interfaces

    def _find_type_aliases(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse TypeScript type alias declarations."""
        type_aliases: list[dict[str, Any]] = []
        for node, capture_name in execute_query(
            self.language, TS_QUERIES["type_aliases"], root_node
        ):
            if capture_name != "type_alias_node":
                continue
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue
            alias_data = {
                "name": self._get_node_text(name_node),
                "line_number": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
            }
            if self.index_source:
                alias_data["source"] = self._get_node_text(node)
            type_aliases.append(alias_data)
        return type_aliases

    def _find_enums(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse TypeScript enum declarations."""
        enums: list[dict[str, Any]] = []
        for node, capture_name in execute_query(
            self.language, TS_QUERIES["enums"], root_node
        ):
            if capture_name != "name":
                continue
            name = self._get_node_text(node)
            enum_node = node.parent
            enums.append(
                {
                    "name": name,
                    "line_number": (
                        enum_node.start_point[0] + 1
                        if enum_node
                        else node.start_point[0] + 1
                    ),
                    "type": "enum",
                    "lang": self.language_name,
                }
            )
        return enums

    def _find_imports(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse TypeScript ES module and CommonJS imports."""
        imports: list[dict[str, Any]] = []
        for node, capture_name in execute_query(
            self.language, TS_QUERIES["imports"], root_node
        ):
            if capture_name != "import":
                continue
            line_number = node.start_point[0] + 1
            if node.type == "import_statement":
                imports.extend(self._parse_es_import(node, line_number))
            elif node.type == "call_expression":
                import_data = self._parse_require_import(node, line_number)
                if import_data is not None:
                    imports.append(import_data)
        return imports

    def _parse_es_import(self, node: Any, line_number: int) -> list[dict[str, Any]]:
        """Parse a TypeScript ES module import statement."""
        source = self._get_node_text(node.child_by_field_name("source")).strip("'\"")
        import_clause = node.child_by_field_name("import")
        if not import_clause:
            return [
                {
                    "name": source,
                    "source": source,
                    "alias": None,
                    "line_number": line_number,
                    "lang": self.language_name,
                }
            ]
        if import_clause.type == "identifier":
            return [
                {
                    "name": "default",
                    "source": source,
                    "alias": self._get_node_text(import_clause),
                    "line_number": line_number,
                    "lang": self.language_name,
                }
            ]
        if import_clause.type == "namespace_import":
            alias_node = import_clause.child_by_field_name("alias")
            if alias_node:
                return [
                    {
                        "name": "*",
                        "source": source,
                        "alias": self._get_node_text(alias_node),
                        "line_number": line_number,
                        "lang": self.language_name,
                    }
                ]
            return []
        if import_clause.type == "named_imports":
            named_imports: list[dict[str, Any]] = []
            for specifier in import_clause.children:
                if specifier.type == "import_specifier":
                    name_node = specifier.child_by_field_name("name")
                    alias_node = specifier.child_by_field_name("alias")
                    if name_node:
                        named_imports.append(
                            {
                                "name": self._get_node_text(name_node),
                                "source": source,
                                "alias": (
                                    self._get_node_text(alias_node)
                                    if alias_node
                                    else None
                                ),
                                "line_number": line_number,
                                "lang": self.language_name,
                            }
                        )
            return named_imports
        return []

    def _parse_require_import(
        self, node: Any, line_number: int
    ) -> dict[str, Any] | None:
        """Parse a TypeScript ``require()`` import expression."""
        args = node.child_by_field_name("arguments")
        if not args or args.named_child_count == 0:
            return None
        source_node = args.named_child(0)
        if not source_node or source_node.type != "string":
            return None
        source = self._get_node_text(source_node).strip("'\"")
        alias = None
        if node.parent.type == "variable_declarator":
            alias_node = node.parent.child_by_field_name("name")
            if alias_node:
                alias = self._get_node_text(alias_node)
        return {
            "name": source,
            "source": source,
            "alias": alias,
            "line_number": line_number,
            "lang": self.language_name,
        }

    def _find_calls(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse TypeScript call and constructor expressions."""
        calls: list[dict[str, Any]] = []
        for node, capture_name in execute_query(
            self.language, TS_QUERIES["calls"], root_node
        ):
            if capture_name != "name":
                continue
            call_node = node.parent
            while call_node and call_node.type not in (
                "call_expression",
                "new_expression",
                "program",
            ):
                call_node = call_node.parent
            arguments_node = (
                call_node.child_by_field_name("arguments") if call_node else None
            )
            args = [
                self._get_node_text(arg)
                for arg in (arguments_node.children if arguments_node else [])
                if arg.type not in ("(", ")", ",")
            ]
            calls.append(
                {
                    "name": self._get_node_text(node),
                    "full_name": (
                        self._get_node_text(call_node)
                        if call_node
                        else self._get_node_text(node)
                    ),
                    "line_number": node.start_point[0] + 1,
                    "args": args,
                    "inferred_obj_type": None,
                    "context": self._get_parent_context(node),
                    "class_context": self._get_parent_context(
                        node,
                        ("class_declaration", "abstract_class_declaration"),
                    ),
                    "lang": self.language_name,
                    "is_dependency": False,
                }
            )
        return calls

    def _find_variables(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse TypeScript variable declarations that are not functions."""
        variables: list[dict[str, Any]] = []
        for node, capture_name in execute_query(
            self.language, TS_QUERIES["variables"], root_node
        ):
            if capture_name != "name":
                continue
            var_node = node.parent
            value_node = var_node.child_by_field_name("value") if var_node else None
            if value_node and value_node.type in (
                "function_expression",
                "arrow_function",
            ):
                continue
            value = None
            if value_node is not None:
                if value_node.type == "call_expression":
                    func_node = value_node.child_by_field_name("function")
                    value = (
                        self._get_node_text(func_node)
                        if func_node
                        else self._get_node_text(node)
                    )
                else:
                    value = self._get_node_text(value_node)
            context, context_type, _ = self._get_parent_context(node)
            variables.append(
                {
                    "name": self._get_node_text(node),
                    "line_number": node.start_point[0] + 1,
                    "value": value,
                    "type": None,
                    "context": context,
                    "class_context": (
                        context if context_type == "class_declaration" else None
                    ),
                    "lang": self.language_name,
                    "is_dependency": False,
                }
            )
        return variables
