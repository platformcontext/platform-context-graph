"""Elixir tree-sitter parser compatibility facade."""

from pathlib import Path
from typing import Any

from .elixir_support import (
    ELIXIR_KEYWORDS,
    ELIXIR_QUERIES,
    FUNCTION_KEYWORDS,
    IMPORT_KEYWORDS,
    MODULE_KEYWORDS,
    pre_scan_elixir,
)


class ElixirTreeSitterParser:
    """Parse Elixir source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Store the parser wrapper used to parse Elixir source.

        Args:
            generic_parser_wrapper: Wrapper providing the parser and language.
        """
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "elixir"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def _get_node_text(self, node: Any) -> str:
        """Decode a tree-sitter node to UTF-8 text.

        Args:
            node: Tree-sitter node to decode.

        Returns:
            UTF-8 decoded node text.
        """
        return node.text.decode("utf-8")

    def _get_parent_context(
        self, node: Any
    ) -> tuple[str | None, str | None, int | None]:
        """Find the nearest enclosing Elixir module or function.

        Args:
            node: Tree-sitter node whose parent context is needed.

        Returns:
            Tuple of context name, context type, and 1-based line number.
        """
        curr = node.parent
        while curr:
            if curr.type == "call":
                for child in curr.children:
                    if child.type != "identifier":
                        continue
                    keyword = self._get_node_text(child)
                    if keyword in MODULE_KEYWORDS:
                        for arg_child in curr.children:
                            if arg_child.type != "arguments":
                                continue
                            for argument_child in arg_child.children:
                                if argument_child.type == "alias":
                                    return (
                                        self._get_node_text(argument_child),
                                        "module",
                                        curr.start_point[0] + 1,
                                    )
                    elif keyword in FUNCTION_KEYWORDS:
                        for arg_child in curr.children:
                            if arg_child.type != "arguments":
                                continue
                            for argument_child in arg_child.children:
                                if argument_child.type == "call":
                                    name_node = argument_child.child_by_field_name(
                                        "target"
                                    )
                                    if name_node:
                                        return (
                                            self._get_node_text(name_node),
                                            "function",
                                            curr.start_point[0] + 1,
                                        )
                    break
            curr = curr.parent
        return None, None, None

    def _enclosing_module_name(self, node: Any) -> str | None:
        """Find the nearest enclosing Elixir module name.

        Args:
            node: Tree-sitter node whose enclosing module is needed.

        Returns:
            Module name when present, otherwise ``None``.
        """
        curr = node.parent
        while curr:
            if curr.type == "call":
                for child in curr.children:
                    if child.type != "identifier":
                        continue
                    keyword = self._get_node_text(child)
                    if keyword in MODULE_KEYWORDS:
                        for arg_child in curr.children:
                            if arg_child.type != "arguments":
                                continue
                            for argument_child in arg_child.children:
                                if argument_child.type == "alias":
                                    return self._get_node_text(argument_child)
                    break
            curr = curr.parent
        return None

    def _calculate_complexity(self, node: Any) -> int:
        """Calculate a simple cyclomatic complexity score for Elixir code.

        Args:
            node: Tree-sitter node representing a function body.

        Returns:
            Cyclomatic complexity estimate starting at 1.
        """
        complexity_keywords = {
            "if",
            "unless",
            "case",
            "cond",
            "with",
            "for",
            "try",
            "receive",
            "and",
            "or",
            "&&",
            "||",
            "when",
        }
        count = 1

        def traverse(current: Any) -> None:
            """Traverse an Elixir AST subtree and update complexity state."""
            nonlocal count
            if (
                current.type == "identifier"
                and self._get_node_text(current) in complexity_keywords
            ):
                count += 1
            elif current.type == "binary_operator":
                op_text = self._get_node_text(current)
                if (
                    "&&" in op_text
                    or "||" in op_text
                    or " and " in op_text
                    or " or " in op_text
                ):
                    count += 1
            for child in current.children:
                traverse(child)

        traverse(node)
        return count

    def _get_docstring(self, node: Any) -> str | None:
        """Extract the nearest Elixir documentation attribute or comment.

        Args:
            node: Function or module call node.

        Returns:
            Docstring-like text when found, otherwise ``None``.
        """
        previous = node.prev_sibling
        while previous:
            if previous.type == "unary_operator":
                text = self._get_node_text(previous)
                if text.startswith("@doc") or text.startswith("@moduledoc"):
                    return text.strip()
            elif previous.type == "comment":
                return self._get_node_text(previous).strip()
            else:
                break
            previous = previous.prev_sibling
        return None

    def parse(
        self,
        path: Path,
        is_dependency: bool = False,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Parse an Elixir file into the standard graph-friendly structure.

        Args:
            path: File path to parse.
            is_dependency: Whether the file belongs to dependency code.
            index_source: Whether to store raw source text on nodes.

        Returns:
            Parsed Elixir modules, functions, imports, and calls.
        """
        self.index_source = index_source
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            source_code = handle.read()

        tree = self.parser.parse(bytes(source_code, "utf8"))
        root_node = tree.root_node

        return {
            "path": str(path),
            "functions": self._find_functions(root_node),
            "classes": [],
            "variables": [],
            "imports": self._find_imports(root_node),
            "function_calls": self._find_calls(root_node),
            "is_dependency": is_dependency,
            "lang": self.language_name,
            "modules": self._find_modules(root_node),
        }

    def _find_modules(self, root_node: Any) -> list[dict[str, Any]]:
        """Find all module-like Elixir definitions.

        Args:
            root_node: Tree-sitter root node.

        Returns:
            Parsed module metadata.
        """
        modules: list[dict[str, Any]] = []
        self._find_modules_recursive(root_node, modules)
        return modules

    def _find_modules_recursive(self, node: Any, modules: list[dict[str, Any]]) -> None:
        """Recursively collect Elixir module-like definitions.

        Args:
            node: Current tree-sitter node.
            modules: Mutable list to populate with parsed modules.
        """
        if node.type == "call":
            keyword = None
            name = None
            has_do_block = False

            for child in node.children:
                if child.type == "identifier":
                    kw = self._get_node_text(child)
                    if kw in MODULE_KEYWORDS:
                        keyword = kw
                elif child.type == "arguments" and keyword:
                    for argument_child in child.children:
                        if argument_child.type == "alias":
                            name = self._get_node_text(argument_child)
                            break
                elif child.type == "do_block":
                    has_do_block = True

            if keyword and name and has_do_block:
                module_data = {
                    "name": name,
                    "line_number": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "lang": self.language_name,
                    "is_dependency": False,
                    "type": keyword,
                }
                if self.index_source:
                    module_data["source"] = self._get_node_text(node)
                modules.append(module_data)

        for child in node.children:
            self._find_modules_recursive(child, modules)

    def _find_functions(self, root_node: Any) -> list[dict[str, Any]]:
        """Find all Elixir function-like definitions.

        Args:
            root_node: Tree-sitter root node.

        Returns:
            Parsed function metadata.
        """
        functions: list[dict[str, Any]] = []
        self._find_functions_recursive(root_node, functions)
        return functions

    def _find_functions_recursive(
        self, node: Any, functions: list[dict[str, Any]]
    ) -> None:
        """Recursively collect Elixir function-like definitions.

        Args:
            node: Current tree-sitter node.
            functions: Mutable list to populate with parsed functions.
        """
        if node.type == "call":
            keyword = None
            func_name = None
            args: list[str] = []

            for child in node.children:
                if child.type == "identifier":
                    kw = self._get_node_text(child)
                    if kw in FUNCTION_KEYWORDS:
                        keyword = kw
                elif child.type == "arguments" and keyword:
                    for argument_child in child.children:
                        if argument_child.type == "call":
                            target = argument_child.child_by_field_name("target")
                            if target:
                                func_name = self._get_node_text(target)
                            for nested_child in argument_child.children:
                                if nested_child.type == "arguments":
                                    for arg in nested_child.children:
                                        if arg.type not in (",", "(", ")"):
                                            args.append(self._get_node_text(arg))
                        elif argument_child.type == "identifier" and not func_name:
                            func_name = self._get_node_text(argument_child)

            if keyword and func_name:
                module_name = self._enclosing_module_name(node)
                function_data = {
                    "name": func_name,
                    "line_number": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "args": args,
                    "lang": self.language_name,
                    "is_dependency": False,
                    "visibility": "private" if keyword.endswith("p") else "public",
                    "type": keyword,
                }
                if self.index_source:
                    function_data["source"] = self._get_node_text(node)
                    function_data["docstring"] = self._get_docstring(node)
                if module_name:
                    function_data["context"] = module_name
                    function_data["context_type"] = "module"
                    function_data["class_context"] = module_name
                functions.append(function_data)

        for child in node.children:
            self._find_functions_recursive(child, functions)

    def _find_imports(self, root_node: Any) -> list[dict[str, Any]]:
        """Find all Elixir import-like statements.

        Args:
            root_node: Tree-sitter root node.

        Returns:
            Parsed import metadata.
        """
        imports: list[dict[str, Any]] = []
        self._find_imports_recursive(root_node, imports)
        return imports

    def _find_imports_recursive(self, node: Any, imports: list[dict[str, Any]]) -> None:
        """Recursively collect Elixir import-like statements.

        Args:
            node: Current tree-sitter node.
            imports: Mutable list to populate with parsed imports.
        """
        if node.type == "call":
            keyword = None
            path = None

            for child in node.children:
                if child.type == "identifier":
                    kw = self._get_node_text(child)
                    if kw in IMPORT_KEYWORDS:
                        keyword = kw
                elif child.type == "arguments" and keyword:
                    for argument_child in child.children:
                        if argument_child.type == "alias":
                            path = self._get_node_text(argument_child)
                            break

            if keyword and path:
                imports.append(
                    {
                        "name": path,
                        "full_import_name": f"{keyword} {path}",
                        "line_number": node.start_point[0] + 1,
                        "alias": path.split(".")[-1] if keyword == "alias" else None,
                        "lang": self.language_name,
                        "is_dependency": False,
                        "import_type": keyword,
                    }
                )

        for child in node.children:
            self._find_imports_recursive(child, imports)

    def _find_calls(self, root_node: Any) -> list[dict[str, Any]]:
        """Find all Elixir call expressions excluding control keywords.

        Args:
            root_node: Tree-sitter root node.

        Returns:
            Parsed call metadata.
        """
        calls: list[dict[str, Any]] = []
        self._find_calls_recursive(root_node, calls)
        return calls

    def _find_calls_recursive(self, node: Any, calls: list[dict[str, Any]]) -> None:
        """Recursively collect Elixir call expressions.

        Args:
            node: Current tree-sitter node.
            calls: Mutable list to populate with parsed calls.
        """
        if node.type == "call":
            target = None
            receiver = None
            name = None
            args: list[str] = []

            for child in node.children:
                if child.type == "dot":
                    left = child.child_by_field_name("left")
                    right = child.child_by_field_name("right")
                    if left:
                        receiver = self._get_node_text(left)
                    if right:
                        name = self._get_node_text(right)
                elif child.type == "identifier" and target is None:
                    target = self._get_node_text(child)
                elif child.type == "arguments":
                    for arg in child.children:
                        if arg.type not in (",", "(", ")"):
                            args.append(self._get_node_text(arg))

            if name and receiver:
                context_name, context_type, context_line = self._get_parent_context(
                    node
                )
                class_context = context_name if context_type == "module" else None
                if context_type == "function":
                    class_context = self._enclosing_module_name(node)
                calls.append(
                    {
                        "name": name,
                        "full_name": f"{receiver}.{name}",
                        "line_number": node.start_point[0] + 1,
                        "args": args,
                        "inferred_obj_type": receiver,
                        "context": (context_name, context_type, context_line),
                        "class_context": class_context,
                        "lang": self.language_name,
                        "is_dependency": False,
                    }
                )
            elif target and target not in ELIXIR_KEYWORDS:
                context_name, context_type, context_line = self._get_parent_context(
                    node
                )
                class_context = context_name if context_type == "module" else None
                if context_type == "function":
                    class_context = self._enclosing_module_name(node)
                calls.append(
                    {
                        "name": target,
                        "full_name": target,
                        "line_number": node.start_point[0] + 1,
                        "args": args,
                        "inferred_obj_type": None,
                        "context": (context_name, context_type, context_line),
                        "class_context": class_context,
                        "lang": self.language_name,
                        "is_dependency": False,
                    }
                )

        for child in node.children:
            self._find_calls_recursive(child, calls)
