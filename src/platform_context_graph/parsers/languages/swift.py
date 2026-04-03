"""Swift tree-sitter parser compatibility facade."""

from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import error_logger, warning_logger
from platform_context_graph.utils.tree_sitter_manager import execute_query

from .swift_support import (
    SWIFT_QUERIES,
    extract_parameter_name,
    get_parent_context,
    pre_scan_swift,
)


class SwiftTreeSitterParser:
    """Parse Swift source files with language-local tree-sitter logic."""

    def __init__(self, generic_parser_wrapper: Any):
        """Store the generic parser wrapper for later use.

        Args:
            generic_parser_wrapper: Wrapper providing language and parser objects.
        """
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "swift"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def parse(
        self,
        path: Path,
        is_dependency: bool = False,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Parse a Swift source file into the standard graph-friendly shape.

        Args:
            path: File path to parse.
            is_dependency: Whether the file is dependency-owned source.
            index_source: Whether parsed nodes should include raw source text.

        Returns:
            Parsed Swift declarations, imports, variables, and calls.
        """
        try:
            self.index_source = index_source
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                source_code = handle.read()

            if not source_code.strip():
                warning_logger(f"Empty or whitespace-only file: {path}")
                return self._empty_result(path, is_dependency)

            tree = self.parser.parse(bytes(source_code, "utf8"))
            parsed_variables = self._parse_variables(
                execute_query(
                    self.language, SWIFT_QUERIES["variables"], tree.root_node
                ),
                path,
            )

            parsed_functions: list[dict[str, Any]] = []
            parsed_classes: list[dict[str, Any]] = []
            parsed_structs: list[dict[str, Any]] = []
            parsed_enums: list[dict[str, Any]] = []
            parsed_protocols: list[dict[str, Any]] = []
            parsed_imports: list[dict[str, Any]] = []
            parsed_calls: list[dict[str, Any]] = []

            for capture_name, query in SWIFT_QUERIES.items():
                if capture_name == "variables":
                    continue
                results = execute_query(self.language, query, tree.root_node)

                if capture_name == "functions":
                    parsed_functions.extend(self._parse_functions(results, path))
                elif capture_name == "classes":
                    classes, structs, enums, protocols = self._parse_classes(
                        results, path
                    )
                    parsed_classes.extend(classes)
                    parsed_structs.extend(structs)
                    parsed_enums.extend(enums)
                    parsed_protocols.extend(protocols)
                elif capture_name == "imports":
                    parsed_imports.extend(self._parse_imports(results))
                elif capture_name == "calls":
                    parsed_calls.extend(self._parse_calls(results, parsed_variables))

            return {
                "path": str(path),
                "functions": parsed_functions,
                "classes": parsed_classes,
                "structs": parsed_structs,
                "enums": parsed_enums,
                "protocols": parsed_protocols,
                "variables": parsed_variables,
                "imports": parsed_imports,
                "function_calls": parsed_calls,
                "is_dependency": is_dependency,
                "lang": self.language_name,
            }
        except Exception as exc:
            error_logger(f"Error parsing Swift file {path}: {exc}")
            return self._empty_result(path, is_dependency)

    def _empty_result(self, path: Path, is_dependency: bool) -> dict[str, Any]:
        """Return the standard empty parse result for Swift files.

        Args:
            path: File path that failed to parse.
            is_dependency: Whether the file is dependency-owned source.

        Returns:
            Empty parse result using the shared output structure.
        """
        return {
            "path": str(path),
            "functions": [],
            "classes": [],
            "structs": [],
            "enums": [],
            "protocols": [],
            "variables": [],
            "imports": [],
            "function_calls": [],
            "is_dependency": is_dependency,
            "lang": self.language_name,
        }

    def _get_node_text(self, node: Any) -> str:
        """Decode a tree-sitter node to UTF-8 text.

        Args:
            node: Tree-sitter node to decode.

        Returns:
            Node text, or an empty string when the node is missing.
        """
        if not node:
            return ""
        return node.text.decode("utf-8")

    def _parse_functions(self, captures: list[Any], path: Path) -> list[dict[str, Any]]:
        """Parse Swift function and initializer declarations.

        Args:
            captures: Query captures for Swift function nodes.
            path: File path being parsed.

        Returns:
            Parsed function metadata.
        """
        functions: list[dict[str, Any]] = []
        seen_nodes: set[tuple[int, int, str]] = set()

        for node, capture_name in captures:
            if capture_name not in ("function_node", "init_node"):
                continue
            node_id = (node.start_byte, node.end_byte, node.type)
            if node_id in seen_nodes:
                continue
            seen_nodes.add(node_id)

            try:
                func_name = "init" if capture_name == "init_node" else None
                if capture_name == "function_node":
                    for child in node.children:
                        if child.type == "simple_identifier":
                            func_name = self._get_node_text(child)
                            break
                if not func_name:
                    continue

                parameters: list[str] = []
                for child in node.children:
                    if child.type == "parameter":
                        param_name = extract_parameter_name(child, self._get_node_text)
                        if param_name:
                            parameters.append(param_name)

                context_name, context_type, _ = get_parent_context(
                    node, self._get_node_text
                )
                function_data = {
                    "name": func_name,
                    "args": parameters,
                    "line_number": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "path": str(path),
                    "lang": self.language_name,
                    "context": context_name,
                    "class_context": (
                        context_name
                        if context_type
                        and ("class" in context_type or "struct" in context_type)
                        else None
                    ),
                }
                if self.index_source:
                    function_data["source"] = self._get_node_text(node)
                functions.append(function_data)
            except Exception as exc:
                error_logger(f"Error parsing function in {path}: {exc}")

        return functions

    def _parse_classes(
        self,
        captures: list[Any],
        path: Path,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        """Parse Swift types into their class-like buckets.

        Args:
            captures: Query captures for Swift type declarations.
            path: File path being parsed.

        Returns:
            Tuple of classes, structs, enums, and protocols.
        """
        classes: list[dict[str, Any]] = []
        structs: list[dict[str, Any]] = []
        enums: list[dict[str, Any]] = []
        protocols: list[dict[str, Any]] = []
        seen_nodes: set[tuple[int, int, str]] = set()

        for node, capture_name in captures:
            if capture_name not in ("class", "struct", "enum", "protocol"):
                continue
            node_id = (node.start_byte, node.end_byte, node.type)
            if node_id in seen_nodes:
                continue
            seen_nodes.add(node_id)

            try:
                type_name = "Anonymous"
                for child in node.children:
                    if child.type == "type_identifier":
                        type_name = self._get_node_text(child)
                        break

                bases: list[str] = []
                for child in node.children:
                    if child.type == "type_inheritance_clause":
                        for subchild in child.children:
                            if subchild.type == "type_identifier":
                                bases.append(self._get_node_text(subchild))

                type_data = {
                    "name": type_name,
                    "line_number": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "bases": bases,
                    "path": str(path),
                    "lang": self.language_name,
                }
                if self.index_source:
                    type_data["source"] = self._get_node_text(node)

                if capture_name == "class":
                    classes.append(type_data)
                elif capture_name == "struct":
                    structs.append(type_data)
                elif capture_name == "enum":
                    enums.append(type_data)
                else:
                    protocols.append(type_data)
            except Exception as exc:
                error_logger(f"Error parsing type in {path}: {exc}")

        return classes, structs, enums, protocols

    def _parse_variables(self, captures: list[Any], path: Path) -> list[dict[str, Any]]:
        """Parse Swift property declarations for later graph edges.

        Args:
            captures: Query captures for property declarations.
            path: File path being parsed.

        Returns:
            Parsed variable metadata.
        """
        variables: list[dict[str, Any]] = []
        seen_vars: set[tuple[str, int]] = set()

        for node, capture_name in captures:
            if capture_name not in ("variable", "constant", "pattern"):
                continue
            try:
                ctx_name, ctx_type, _ = get_parent_context(node, self._get_node_text)
                var_name = "unknown"
                var_type = "Unknown"

                if capture_name == "pattern":
                    var_name = self._get_node_text(node)
                else:
                    for child in node.children:
                        if child.type == "simple_identifier":
                            var_name = self._get_node_text(child)
                            break
                        if child.type == "pattern_binding":
                            for subchild in child.children:
                                if subchild.type == "simple_identifier":
                                    var_name = self._get_node_text(subchild)
                                    break

                for child in node.children:
                    if child.type == "type_annotation":
                        for subchild in child.children:
                            if subchild.type == "type_identifier":
                                var_type = self._get_node_text(subchild)
                                break

                if var_name == "unknown":
                    continue
                var_key = (var_name, node.start_point[0] + 1)
                if var_key in seen_vars:
                    continue
                seen_vars.add(var_key)
                variables.append(
                    {
                        "name": var_name,
                        "type": var_type,
                        "line_number": node.start_point[0] + 1,
                        "path": str(path),
                        "lang": self.language_name,
                        "context": ctx_name,
                        "class_context": (
                            ctx_name
                            if ctx_type
                            and ("class" in ctx_type or "struct" in ctx_type)
                            else None
                        ),
                    }
                )
            except Exception:
                continue

        return variables

    def _parse_imports(self, captures: list[Any]) -> list[dict[str, Any]]:
        """Parse Swift import declarations.

        Args:
            captures: Query captures for import declarations.

        Returns:
            Parsed import metadata.
        """
        imports: list[dict[str, Any]] = []

        for node, capture_name in captures:
            if capture_name != "import":
                continue
            try:
                text = self._get_node_text(node)
                parts = text.replace("import ", "").strip().split()
                module_name = parts[0] if parts else ""
                if not module_name:
                    continue
                imports.append(
                    {
                        "name": module_name,
                        "full_import_name": module_name,
                        "line_number": node.start_point[0] + 1,
                        "alias": None,
                        "context": (None, None),
                        "lang": self.language_name,
                        "is_dependency": False,
                    }
                )
            except Exception:
                continue

        return imports

    def _parse_calls(
        self,
        captures: list[Any],
        variables: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Parse Swift function and method calls.

        Args:
            captures: Query captures for call expressions.
            variables: Parsed variables used for simple receiver type inference.

        Returns:
            Parsed call metadata.
        """
        calls: list[dict[str, Any]] = []
        var_map = {
            (variable["name"], variable["context"]): variable["type"]
            for variable in (variables or [])
        }

        for node, capture_name in captures:
            if capture_name != "call_node":
                continue
            try:
                call_name = "unknown"
                base_obj = None
                first_child = node.children[0] if node.children else None
                if first_child:
                    if first_child.type == "simple_identifier":
                        call_name = self._get_node_text(first_child)
                    elif first_child.type == "navigation_expression":
                        for child in first_child.children:
                            if child.type == "simple_identifier":
                                if base_obj is None:
                                    base_obj = self._get_node_text(child)
                                else:
                                    call_name = self._get_node_text(child)

                if call_name == "unknown":
                    continue

                ctx_name, ctx_type, ctx_line = get_parent_context(
                    node, self._get_node_text
                )
                inferred_type = None
                if base_obj:
                    inferred_type = var_map.get((base_obj, ctx_name))
                    if not inferred_type:
                        inferred_type = var_map.get((base_obj, None))
                    if not inferred_type:
                        for (var_name, _), var_type in var_map.items():
                            if var_name == base_obj:
                                inferred_type = var_type
                                break

                calls.append(
                    {
                        "name": call_name,
                        "full_name": (
                            f"{base_obj}.{call_name}" if base_obj else call_name
                        ),
                        "line_number": node.start_point[0] + 1,
                        "args": [],
                        "inferred_obj_type": inferred_type,
                        "context": [None, ctx_type, ctx_line],
                        "class_context": [None, None],
                        "lang": self.language_name,
                        "is_dependency": False,
                    }
                )
            except Exception:
                continue

        return calls
