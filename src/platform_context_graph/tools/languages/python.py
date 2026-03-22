"""Python tree-sitter parser compatibility facade."""

import os
from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import error_logger, info_logger
from platform_context_graph.utils.source_text import read_source_text
from platform_context_graph.utils.tree_sitter_manager import execute_query

from .python_support import (
    PY_QUERIES,
    calculate_complexity,
    convert_notebook_to_temp_python,
    find_dict_method_references,
    get_docstring,
    get_parent_context,
    pre_scan_python,
)


class PythonTreeSitterParser:
    """Parse Python source files with language-local tree-sitter logic."""

    def __init__(self, generic_parser_wrapper: Any):
        """Store the generic parser wrapper for later parse operations.

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
            Node text.
        """
        return node.text.decode("utf-8")

    def _get_parent_context(
        self,
        node: Any,
        types: tuple[str, ...] = ("function_definition", "class_definition"),
    ) -> tuple[str | None, str | None, int | None]:
        """Find the nearest enclosing Python declaration for a node.

        Args:
            node: Tree-sitter node whose parent context is needed.
            types: Node types that count as context boundaries.

        Returns:
            A tuple of context name, context type, and 1-based line number.
        """
        return get_parent_context(node, self._get_node_text, types)

    def parse(
        self,
        path: Path | str,
        is_dependency: bool = False,
        is_notebook: bool = False,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Parse a Python source file into the standard graph-friendly structure.

        Args:
            path: File path to parse.
            is_dependency: Whether the file belongs to dependency code.
            is_notebook: Whether the file should be converted from a notebook.
            index_source: Whether parsed nodes should include raw source text.

        Returns:
            Parsed Python declarations, imports, variables, and calls.
        """
        original_file_path = Path(path)
        temp_py_file: Path | None = None
        self.index_source = index_source

        try:
            path_to_parse = original_file_path
            if is_notebook:
                info_logger(
                    f"Converting notebook {original_file_path} to temporary Python file."
                )
                temp_py_file = convert_notebook_to_temp_python(original_file_path)
                path_to_parse = temp_py_file

            source_code = read_source_text(path_to_parse)

            tree = self.parser.parse(bytes(source_code, "utf8"))
            root_node = tree.root_node

            functions = self._find_functions(root_node)
            functions.extend(self._find_lambda_assignments(root_node))

            return {
                "path": str(original_file_path),
                "functions": functions,
                "classes": self._find_classes(root_node),
                "variables": self._find_variables(root_node),
                "imports": self._find_imports(root_node),
                "function_calls": self._find_calls(root_node),
                "is_dependency": is_dependency,
                "lang": self.language_name,
            }
        except Exception as exc:
            error_logger(f"Failed to parse {original_file_path}: {exc}")
            return {"path": str(original_file_path), "error": str(exc)}
        finally:
            if temp_py_file and temp_py_file.exists():
                os.remove(temp_py_file)
                info_logger(f"Removed temporary file: {temp_py_file}")

    def _find_lambda_assignments(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse Python lambda assignments as function-like nodes.

        Args:
            root_node: Tree-sitter root node.

        Returns:
            Parsed lambda assignment metadata.
        """
        functions: list[dict[str, Any]] = []
        for node, capture_name in execute_query(
            self.language,
            PY_QUERIES["lambda_assignments"],
            root_node,
        ):
            if capture_name != "name":
                continue

            assignment_node = node.parent
            lambda_node = assignment_node.child_by_field_name("right")
            params_node = (
                lambda_node.child_by_field_name("parameters") if lambda_node else None
            )
            context, context_type, _ = self._get_parent_context(assignment_node)
            class_context, _, _ = self._get_parent_context(
                assignment_node,
                ("class_definition",),
            )

            function_data = {
                "name": self._get_node_text(node),
                "line_number": node.start_point[0] + 1,
                "end_line": assignment_node.end_point[0] + 1,
                "args": [
                    self._get_node_text(param)
                    for param in (params_node.children if params_node else [])
                    if param.type == "identifier"
                ],
                "cyclomatic_complexity": 1,
                "context": context,
                "context_type": context_type,
                "class_context": class_context,
                "decorators": [],
                "lang": self.language_name,
                "is_dependency": False,
            }
            if self.index_source:
                function_data["source"] = self._get_node_text(assignment_node)
                function_data["docstring"] = None
            functions.append(function_data)

        return functions

    def _find_functions(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse Python function definitions.

        Args:
            root_node: Tree-sitter root node.

        Returns:
            Parsed function metadata.
        """
        functions: list[dict[str, Any]] = []
        for node, capture_name in execute_query(
            self.language, PY_QUERIES["functions"], root_node
        ):
            if capture_name != "name":
                continue

            func_node = node.parent
            params_node = func_node.child_by_field_name("parameters")
            body_node = func_node.child_by_field_name("body")
            decorators = [
                self._get_node_text(child)
                for child in func_node.children
                if child.type == "decorator"
            ]
            context, context_type, _ = self._get_parent_context(func_node)
            class_context, _, _ = self._get_parent_context(
                func_node, ("class_definition",)
            )

            args: list[str] = []
            for param in (params_node.children if params_node else []):
                arg_text = None
                if param.type == "identifier":
                    arg_text = self._get_node_text(param)
                elif param.type in (
                    "default_parameter",
                    "typed_parameter",
                    "typed_default_parameter",
                ):
                    name_node = param.child_by_field_name("name")
                    if name_node:
                        arg_text = self._get_node_text(name_node)
                elif param.type in ("list_splat_pattern", "dictionary_splat_pattern"):
                    arg_text = self._get_node_text(param)
                if arg_text:
                    args.append(arg_text)

            function_data = {
                "name": self._get_node_text(node),
                "line_number": node.start_point[0] + 1,
                "end_line": func_node.end_point[0] + 1,
                "args": args,
                "cyclomatic_complexity": calculate_complexity(func_node),
                "context": context,
                "context_type": context_type,
                "class_context": class_context,
                "decorators": [decorator for decorator in decorators if decorator],
                "lang": self.language_name,
                "is_dependency": False,
            }
            if self.index_source:
                function_data["source"] = self._get_node_text(func_node)
                function_data["docstring"] = get_docstring(
                    body_node, self._get_node_text
                )
            functions.append(function_data)

        return functions

    def _find_classes(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse Python class definitions.

        Args:
            root_node: Tree-sitter root node.

        Returns:
            Parsed class metadata.
        """
        classes: list[dict[str, Any]] = []
        for node, capture_name in execute_query(
            self.language, PY_QUERIES["classes"], root_node
        ):
            if capture_name != "name":
                continue

            class_node = node.parent
            body_node = class_node.child_by_field_name("body")
            superclasses_node = class_node.child_by_field_name("superclasses")
            bases = [
                self._get_node_text(child)
                for child in (superclasses_node.children if superclasses_node else [])
                if child.type in ("identifier", "attribute")
            ]
            decorators = [
                self._get_node_text(child)
                for child in class_node.children
                if child.type == "decorator"
            ]
            context, _, _ = self._get_parent_context(class_node)

            class_data = {
                "name": self._get_node_text(node),
                "line_number": node.start_point[0] + 1,
                "end_line": class_node.end_point[0] + 1,
                "bases": [base for base in bases if base],
                "context": context,
                "decorators": [decorator for decorator in decorators if decorator],
                "lang": self.language_name,
                "is_dependency": False,
            }
            if self.index_source:
                class_data["source"] = self._get_node_text(class_node)
                class_data["docstring"] = get_docstring(body_node, self._get_node_text)
            classes.append(class_data)

        return classes

    def _find_imports(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse Python import statements.

        Args:
            root_node: Tree-sitter root node.

        Returns:
            Parsed import metadata.
        """
        imports: list[dict[str, Any]] = []
        seen_modules: set[str] = set()

        for node, capture_name in execute_query(
            self.language, PY_QUERIES["imports"], root_node
        ):
            if capture_name == "import":
                node_text = self._get_node_text(node)
                alias = None
                if " as " in node_text:
                    full_name, alias = [
                        part.strip() for part in node_text.split(" as ", 1)
                    ]
                else:
                    full_name = node_text.strip()
                if full_name in seen_modules:
                    continue
                seen_modules.add(full_name)
                imports.append(
                    {
                        "name": full_name,
                        "full_import_name": full_name,
                        "line_number": node.start_point[0] + 1,
                        "alias": alias,
                        "context": self._get_parent_context(node)[:2],
                        "lang": self.language_name,
                        "is_dependency": False,
                    }
                )
            elif capture_name == "from_import_stmt":
                module_name_node = node.child_by_field_name("module_name")
                if not module_name_node:
                    continue
                module_name = self._get_node_text(module_name_node)
                import_list_node = node.child_by_field_name("name")
                if not import_list_node:
                    continue
                for child in import_list_node.children:
                    imported_name = None
                    alias = None
                    if child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        alias_node = child.child_by_field_name("alias")
                        if name_node:
                            imported_name = self._get_node_text(name_node)
                        if alias_node:
                            alias = self._get_node_text(alias_node)
                    elif child.type in ("dotted_name", "identifier"):
                        imported_name = self._get_node_text(child)

                    if not imported_name:
                        continue
                    full_import_name = f"{module_name}.{imported_name}"
                    if full_import_name in seen_modules:
                        continue
                    seen_modules.add(full_import_name)
                    imports.append(
                        {
                            "name": imported_name,
                            "full_import_name": full_import_name,
                            "line_number": child.start_point[0] + 1,
                            "alias": alias,
                            "context": self._get_parent_context(child)[:2],
                            "lang": self.language_name,
                            "is_dependency": False,
                        }
                    )

        return imports

    def _find_calls(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse Python call expressions, including indirect dictionary calls.

        Args:
            root_node: Tree-sitter root node.

        Returns:
            Parsed call metadata.
        """
        calls: list[dict[str, Any]] = []
        for node, capture_name in execute_query(
            self.language, PY_QUERIES["calls"], root_node
        ):
            if capture_name != "name":
                continue

            call_node = (
                node.parent if node.parent.type == "call" else node.parent.parent
            )
            full_call_node = call_node.child_by_field_name("function")
            arguments_node = call_node.child_by_field_name("arguments")
            args = [
                self._get_node_text(arg)
                for arg in (arguments_node.children if arguments_node else [])
                if self._get_node_text(arg) not in ("", "(", ")", ",")
            ]
            calls.append(
                {
                    "name": self._get_node_text(node),
                    "full_name": self._get_node_text(full_call_node),
                    "line_number": node.start_point[0] + 1,
                    "args": args,
                    "inferred_obj_type": None,
                    "context": self._get_parent_context(node),
                    "class_context": self._get_parent_context(
                        node, ("class_definition",)
                    )[:2],
                    "lang": self.language_name,
                    "is_dependency": False,
                }
            )

        calls.extend(
            find_dict_method_references(
                self.language,
                root_node,
                self.language_name,
                self._get_node_text,
                self._get_parent_context,
            )
        )
        return calls

    def _find_variables(self, root_node: Any) -> list[dict[str, Any]]:
        """Parse Python assignment targets as variables.

        Args:
            root_node: Tree-sitter root node.

        Returns:
            Parsed variable metadata.
        """
        variables: list[dict[str, Any]] = []
        for node, capture_name in execute_query(
            self.language, PY_QUERIES["variables"], root_node
        ):
            if capture_name != "name":
                continue

            assignment_node = node.parent
            right_node = assignment_node.child_by_field_name("right")
            if right_node and right_node.type == "lambda":
                continue

            type_node = assignment_node.child_by_field_name("type")
            context, _, _ = self._get_parent_context(node)
            class_context, _, _ = self._get_parent_context(node, ("class_definition",))
            variables.append(
                {
                    "name": self._get_node_text(node),
                    "line_number": node.start_point[0] + 1,
                    "value": self._get_node_text(right_node) if right_node else None,
                    "type": self._get_node_text(type_node) if type_node else None,
                    "context": context,
                    "class_context": class_context,
                    "lang": self.language_name,
                    "is_dependency": False,
                }
            )

        return variables
