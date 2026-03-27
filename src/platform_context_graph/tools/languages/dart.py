"""Tree-sitter parser support for Dart."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from platform_context_graph.utils.debug_log import (
    debug_log,
    error_logger,
    info_logger,
    warning_logger,
)
from platform_context_graph.utils.tree_sitter_manager import execute_query

DART_QUERIES = {
    "functions": """
        (function_signature
            name: (identifier) @name
            (formal_parameter_list) @params
        ) @function_node
        (constructor_signature
            name: (identifier) @name
            (formal_parameter_list) @params
        ) @function_node
    """,
    "classes": """
        [
            (class_definition name: (identifier) @name)
            (mixin_declaration (identifier) @name)
            (extension_declaration name: (identifier) @name)
            (enum_declaration name: (identifier) @name)
        ] @class
    """,
    "imports": """
        (library_import) @import
        (library_export) @import
    """,
    "calls": """
        (expression_statement
            (identifier) @name
        ) @call
        (selector
            (argument_part (arguments))
        ) @call
    """,
    "variables": """
        (local_variable_declaration
            (initialized_variable_definition
                name: (identifier) @name
            )
        ) @variable
        (declaration
            (initialized_identifier_list
                (initialized_identifier
                    (identifier) @name
                )
            )
        ) @variable
        (initialized_variable_definition
            name: (identifier) @name
        ) @variable
        (static_final_declaration_list
            (static_final_declaration) @variable
        )
        (initialized_identifier_list
            (initialized_identifier
                (identifier) @name
            )
        ) @variable
    """,
}


class DartTreeSitterParser:
    """A Dart-specific parser using tree-sitter, encapsulating language-specific logic."""

    def __init__(self, generic_parser_wrapper):
        """Initialize the Dart parser with the shared tree-sitter wrapper."""
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "dart"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def _get_node_text(self, node) -> str:
        """Decode tree-sitter node text to UTF-8."""
        if not node:
            return ""
        return node.text.decode("utf-8")

    def _get_declaration_name(self, node):
        """Return the declared identifier for class-like Dart nodes."""
        if node is None:
            return None

        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return name_node

        return next((child for child in node.children if child.type == "identifier"), None)

    def _get_signature_context(self, node):
        """Return the callable declaration metadata for one signature node."""
        if node is None:
            return None, None, None

        candidate = node
        if node.type == "method_signature":
            candidate = next(
                (
                    child
                    for child in node.children
                    if child.type
                    in ("function_signature", "constructor_signature", "getter_signature")
                ),
                node,
            )

        if candidate.type not in (
            "function_signature",
            "constructor_signature",
            "getter_signature",
        ):
            return None, None, None

        name_node = self._get_declaration_name(candidate)
        if name_node is None:
            return None, None, None

        return (
            self._get_node_text(name_node),
            candidate.type,
            candidate.start_point[0] + 1,
        )

    def _get_parent_context(
        self,
        node,
        types=(
            "function_signature",
            "method_signature",
            "constructor_signature",
            "getter_signature",
            "class_definition",
            "mixin_declaration",
            "extension_declaration",
        ),
    ):
        """Return the nearest enclosing Dart declaration."""
        curr = node.parent
        while curr:
            if curr.type == "function_body" and curr.parent is not None:
                named_siblings = [child for child in curr.parent.children if child.is_named]
                try:
                    curr_index = named_siblings.index(curr)
                except ValueError:
                    curr_index = -1
                if curr_index > 0:
                    for sibling in reversed(named_siblings[:curr_index]):
                        signature_context = self._get_signature_context(sibling)
                        if signature_context[0] is not None:
                            return signature_context

            if curr.type in types:
                signature_context = self._get_signature_context(curr)
                if signature_context[0] is not None:
                    return signature_context

                name_node = self._get_declaration_name(curr)
                return (
                    self._get_node_text(name_node) if name_node else None,
                    curr.type,
                    curr.start_point[0] + 1,
                )
            curr = curr.parent
        return None, None, None

    def _calculate_complexity(self, node):
        """Estimate cyclomatic complexity for a Dart AST node."""
        complexity_nodes = {
            "if_statement",
            "for_statement",
            "while_statement",
            "do_statement",
            "switch_statement",
            "switch_case",
            "if_element",
            "for_element",
            "conditional_expression",
            "binary_expression",
            "catch_clause",
        }
        count = 1

        def traverse(n):
            """Traverse a Dart AST subtree and update complexity state."""
            nonlocal count
            if n.type in complexity_nodes:
                if n.type == "binary_expression":
                    op = n.child_by_field_name("operator")
                    if op and self._get_node_text(op) in ("&&", "||"):
                        count += 1
                else:
                    count += 1
            for child in n.children:
                traverse(child)

        traverse(node)
        return count

    def parse(
        self, path: Path, is_dependency: bool = False, index_source: bool = False
    ) -> Dict:
        """Parses a Dart file and returns its structure in a standardized dictionary format."""
        self.index_source = index_source
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                source_code = f.read()

            tree = self.parser.parse(bytes(source_code, "utf8"))
            root_node = tree.root_node

            functions = self._find_functions(root_node)
            classes = self._find_classes(root_node)
            imports = self._find_imports(root_node, source_code)
            function_calls = self._find_calls(root_node)
            variables = self._find_variables(root_node)

            return {
                "path": str(path),
                "functions": functions,
                "classes": classes,
                "variables": variables,
                "imports": imports,
                "function_calls": function_calls,
                "is_dependency": is_dependency,
                "lang": self.language_name,
            }
        except Exception as e:
            error_logger(f"Failed to parse Dart file {path}: {e}")
            return {"path": str(path), "error": str(e)}

    def _find_functions(self, root_node):
        """Find Dart function and method declarations in the parse tree."""
        functions = []
        seen_nodes = set()
        query_str = DART_QUERIES["functions"]

        for node, capture_name in execute_query(self.language, query_str, root_node):
            if capture_name == "function_node":
                node_id = (node.start_byte, node.end_byte)
                if node_id in seen_nodes:
                    continue
                seen_nodes.add(node_id)

                name_node = node.child_by_field_name("name")
                if name_node is None and node.type == "mixin_declaration":
                    name_node = next(
                        (child for child in node.children if child.type == "identifier"),
                        None,
                    )
                if not name_node:
                    continue

                name = self._get_node_text(name_node)
                params_node = node.child_by_field_name(
                    "parameters"
                ) or node.child_by_field_name("formal_parameter_list")

                args = []
                if params_node:
                    for child in params_node.children:
                        if child.type == "formal_parameter":
                            # Extract parameter name
                            # can be 'int x', 'var x', 'final x', 'x', 'this.x'
                            p_name = self._extract_param_name(child)
                            if p_name:
                                args.append(p_name)

                # Find body to get complexity and end_line
                # In Dart, body is often a sibling of signature
                body_node = None
                parent = node.parent
                if parent:
                    # Look for function_body among siblings after the signature
                    found_sig = False
                    for child in parent.children:
                        if child == node:
                            found_sig = True
                            continue
                        if found_sig:
                            if child.type == "function_body":
                                body_node = child
                                break
                            elif child.type in (
                                "function_signature",
                                "method_signature",
                                "declaration",
                                "class_definition",
                            ):
                                # Hit another signature or declaration, stop looking
                                break

                context, context_type, context_line = self._get_parent_context(node)
                # Check if it's in a class
                class_context = None
                curr = node.parent
                while curr:
                    if curr.type == "class_definition":
                        cn = curr.child_by_field_name("name")
                        class_context = self._get_node_text(cn) if cn else None
                        break
                    curr = curr.parent

                func_data = {
                    "name": name,
                    "line_number": node.start_point[0] + 1,
                    "end_line": (body_node or node).end_point[0] + 1,
                    "args": args,
                    "cyclomatic_complexity": (
                        self._calculate_complexity(body_node) if body_node else 1
                    ),
                    "context": context,
                    "context_type": context_type,
                    "class_context": class_context,
                    "lang": self.language_name,
                    "is_dependency": False,
                }
                if self.index_source:
                    func_data["source"] = self._get_node_text(node) + (
                        self._get_node_text(body_node) if body_node else ""
                    )

                functions.append(func_data)
        return functions

    def _extract_param_name(self, param_node) -> Optional[str]:
        """Extract a Dart parameter name from a formal parameter node."""

        # formal_parameter -> normal_parameter -> ... -> identifier
        # or formal_parameter -> constructor_param -> this.identifier
        def find_id(n):
            """Recursively locate the first identifier below a node."""
            if n.type == "identifier":
                return self._get_node_text(n)
            for child in n.children:
                res = find_id(child)
                if res:
                    return res
            return None

        return find_id(param_node)

    def _find_classes(self, root_node):
        """Find Dart class-like declarations."""
        classes = []
        query_str = DART_QUERIES["classes"]
        for node, capture_name in execute_query(self.language, query_str, root_node):
            if capture_name == "class":
                name_node = self._get_declaration_name(node)
                if not name_node:
                    continue

                name = self._get_node_text(name_node)

                # Bases (implements, extends, with)
                bases = []
                # This is simplified, can be improved by navigating children
                for child in node.children:
                    if child.type in ("superclass", "interfaces", "mixins"):
                        for sub in child.children:
                            if sub.type in ("type_identifier", "type_not_void"):
                                bases.append(self._get_node_text(sub))

                class_data = {
                    "name": name,
                    "line_number": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "bases": bases,
                    "lang": self.language_name,
                    "is_dependency": False,
                }
                if self.index_source:
                    class_data["source"] = self._get_node_text(node)

                classes.append(class_data)
        return classes

    def _find_imports(self, root_node, source_code):
        """Find Dart import and export directives."""
        imports = []
        query_str = DART_QUERIES["imports"]
        for node, capture_name in execute_query(self.language, query_str, root_node):
            if capture_name == "import":
                # Find URI
                uri_node = None

                def find_uri(n):
                    """Locate the first URI node in the import subtree."""
                    nonlocal uri_node
                    if n.type == "uri":
                        uri_node = n
                        return
                    for child in n.children:
                        find_uri(child)
                        if uri_node:
                            return

                find_uri(node)
                if uri_node:
                    uri_text = self._get_node_text(uri_node).strip("'\"")

                    # Handle 'as' alias
                    alias = None
                    for child in node.children:
                        if child.type == "import_specification":
                            for sub in child.children:
                                if sub.type == "prefix":
                                    alias_node = sub.child_by_field_name("identifier")
                                    if alias_node:
                                        alias = self._get_node_text(alias_node)

                    imports.append(
                        {
                            "name": uri_text,
                            "full_import_name": uri_text,
                            "line_number": node.start_point[0] + 1,
                            "alias": alias,
                            "lang": self.language_name,
                            "is_dependency": False,
                        }
                    )
        return imports

    def _find_calls(self, root_node):
        """Find Dart call expressions."""
        calls = []
        seen_calls = set()

        def extract_arguments(selector_node):
            """Return argument texts from a selector that carries call arguments."""

            argument_part = next(
                (child for child in selector_node.children if child.type == "argument_part"),
                None,
            )
            arguments_node = None
            if argument_part is not None:
                arguments_node = next(
                    (child for child in argument_part.children if child.type == "arguments"),
                    None,
                )
            elif selector_node.type == "arguments":
                arguments_node = selector_node

            args = []
            if arguments_node is None:
                return args

            for child in arguments_node.children:
                if child.type not in ("(", ")", ","):
                    args.append(self._get_node_text(child))
            return args

        def selector_member_name(selector_node):
            """Return the member name from a dotted selector like `.map`."""

            for child in selector_node.children:
                if child.type == "unconditional_assignable_selector":
                    for sub in child.children:
                        if sub.type == "identifier":
                            return sub
            return None

        def maybe_record_call(name_node, *, full_name, selector_node):
            """Record one Dart call if it has not been seen yet."""

            name = self._get_node_text(name_node)
            line_number = name_node.start_point[0] + 1
            call_key = (name, full_name, line_number)
            if call_key in seen_calls:
                return
            seen_calls.add(call_key)

            context, context_type, context_line = self._get_parent_context(name_node)
            class_context = None
            curr = name_node.parent
            while curr:
                if curr.type in (
                    "class_definition",
                    "mixin_declaration",
                    "extension_declaration",
                ):
                    class_name_node = self._get_declaration_name(curr)
                    class_context = (
                        self._get_node_text(class_name_node)
                        if class_name_node is not None
                        else None
                    )
                    break
                curr = curr.parent

            calls.append(
                {
                    "name": name,
                    "full_name": full_name,
                    "line_number": line_number,
                    "args": extract_arguments(selector_node),
                    "context": (context, context_type, context_line),
                    "class_context": class_context,
                    "lang": self.language_name,
                    "is_dependency": False,
                }
            )

        def walk(node):
            """Traverse the Dart tree and collect function-style calls."""

            children = [child for child in node.children if child.is_named]
            for idx, child in enumerate(children):
                if child.type == "identifier":
                    if (
                        idx + 1 < len(children)
                        and children[idx + 1].type == "selector"
                        and extract_arguments(children[idx + 1]) is not None
                        and extract_arguments(children[idx + 1]) is not None
                    ):
                        args = extract_arguments(children[idx + 1])
                        if args or any(
                            grandchild.type == "arguments"
                            for grandchild in children[idx + 1].children
                        ):
                            maybe_record_call(
                                child,
                                full_name=self._get_node_text(child),
                                selector_node=children[idx + 1],
                            )
                    if idx + 2 < len(children):
                        member_name_node = selector_member_name(children[idx + 1])
                        if (
                            children[idx + 1].type == "selector"
                            and member_name_node is not None
                            and children[idx + 2].type == "selector"
                        ):
                            args = extract_arguments(children[idx + 2])
                            if args or any(
                                grandchild.type == "arguments"
                                for grandchild in children[idx + 2].children
                            ):
                                maybe_record_call(
                                    member_name_node,
                                    full_name=(
                                        f"{self._get_node_text(child)}."
                                        f"{self._get_node_text(member_name_node)}"
                                    ),
                                    selector_node=children[idx + 2],
                                )
                walk(child)

        walk(root_node)
        return calls

    def _find_variables(self, root_node):
        """Find Dart variable declarations."""
        variables = []
        query_str = DART_QUERIES["variables"]
        for node, capture_name in execute_query(self.language, query_str, root_node):
            if capture_name == "name":
                name = self._get_node_text(node)
                context, _, _ = self._get_parent_context(node)

                variables.append(
                    {
                        "name": name,
                        "line_number": node.start_point[0] + 1,
                        "context": context,
                        "lang": self.language_name,
                        "is_dependency": False,
                    }
                )
        return variables


def pre_scan_dart(files: List[Path], parser_wrapper) -> Dict[str, List[str]]:
    """Scans Dart files to create a map of class/function names to their file paths."""
    name_to_files = {}
    query_str = """
        [
            (class_definition name: (identifier) @name)
            (mixin_declaration name: (identifier) @name)
            (extension_declaration name: (identifier) @name)
            (function_signature name: (identifier) @name)
        ]
    """
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            tree = parser_wrapper.parser.parse(bytes(content, "utf8"))
            for node, _ in execute_query(
                parser_wrapper.language, query_str, tree.root_node
            ):
                name = node.text.decode("utf-8")
                if name not in name_to_files:
                    name_to_files[name] = []
                name_to_files[name].append(str(path.resolve()))
        except Exception as e:
            warning_logger(f"Error pre-scanning Dart file {path}: {e}")
    return name_to_files
