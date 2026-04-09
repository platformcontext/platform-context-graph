"""Support helpers for the handwritten Python parser."""

import ast
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Callable
import warnings

import nbformat
from nbconvert import PythonExporter

from platform_context_graph.utils.debug_log import warning_logger
from platform_context_graph.utils.source_text import read_source_text
from platform_context_graph.utils.tree_sitter_manager import execute_query

logging.getLogger("traitlets").setLevel(logging.WARNING)
logging.getLogger("nbconvert").setLevel(logging.WARNING)
warnings.filterwarnings(
    "ignore",
    message=".*IPython is needed to transform IPython syntax.*",
)

PY_QUERIES = {
    "imports": """
        (import_statement name: (_) @import)
        (import_from_statement) @from_import_stmt
    """,
    "classes": """
        (class_definition
            name: (identifier) @name
            superclasses: (argument_list)? @superclasses
            body: (block) @body)
    """,
    "functions": """
        (function_definition
            name: (identifier) @name
            parameters: (parameters) @parameters
            body: (block) @body
            return_type: (_)? @return_type)
    """,
    "calls": """
        (call
            function: (identifier) @name)
        (call
            function: (attribute attribute: (identifier) @name) @full_call)
    """,
    "variables": """
        (assignment
            left: (identifier) @name)
    """,
    "variables_module": """
        (module
            (assignment left: (identifier) @name))
        (class_definition
            body: (block
                (assignment left: (identifier) @name)))
    """,
    "lambda_assignments": """
        (assignment
            left: (identifier) @name
            right: (lambda) @lambda_node)
    """,
    "docstrings": """
        (expression_statement (string) @docstring)
    """,
    "dict_method_refs": """
        (dictionary
            (pair
                key: (_) @key
                value: (attribute) @method_ref))
    """,
}


def convert_notebook_to_temp_python(path: Path | str) -> Path:
    """Convert a notebook file into a temporary Python file.

    Args:
        path: Notebook path to convert.

    Returns:
        Path to the generated temporary Python file.
    """
    with open(path, "r", encoding="utf-8") as handle:
        notebook_node = nbformat.read(handle, as_version=4)

    try:
        exporter = PythonExporter()
        python_code, _ = exporter.from_notebook_node(notebook_node)
    except Exception:
        python_code = "\n\n".join(
            str(cell.get("source", ""))
            for cell in notebook_node.cells
            if cell.get("cell_type") == "code"
        )
    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        suffix=".py",
        encoding="utf-8",
    ) as temp_file:
        temp_file.write(python_code)
        return Path(temp_file.name)


def get_parent_context(
    node: Any,
    get_node_text: Callable[[Any], str],
    types: tuple[str, ...] = ("function_definition", "class_definition"),
) -> tuple[str | None, str | None, int | None]:
    """Find the nearest enclosing Python declaration for a node.

    Args:
        node: Tree-sitter node whose context is needed.
        get_node_text: Callable that decodes nodes to source text.
        types: Node types that count as parent context boundaries.

    Returns:
        A tuple of context name, context type, and 1-based line number.
    """
    curr = node.parent
    while curr:
        if curr.type in types:
            name_node = curr.child_by_field_name("name")
            return (
                get_node_text(name_node) if name_node else None,
                curr.type,
                curr.start_point[0] + 1,
            )
        curr = curr.parent
    return None, None, None


def calculate_complexity(node: Any) -> int:
    """Estimate cyclomatic complexity for a Python node.

    Args:
        node: Tree-sitter node representing a function body.

    Returns:
        Simple cyclomatic complexity estimate starting at 1.
    """
    complexity_nodes = {
        "if_statement",
        "for_statement",
        "while_statement",
        "except_clause",
        "with_statement",
        "boolean_operator",
        "list_comprehension",
        "generator_expression",
        "case_clause",
    }
    count = 1

    def traverse(current: Any) -> None:
        """Traverse a Python AST subtree and update complexity state."""
        nonlocal count
        if current.type in complexity_nodes:
            count += 1
        for child in current.children:
            traverse(child)

    traverse(node)
    return count


def get_docstring(body_node: Any, get_node_text: Callable[[Any], str]) -> str | None:
    """Extract the first docstring literal from a Python block.

    Args:
        body_node: Tree-sitter block node to inspect.
        get_node_text: Callable that decodes nodes to source text.

    Returns:
        Docstring content when present, otherwise ``None``.
    """
    if body_node and body_node.child_count > 0:
        first_child = body_node.children[0]
        if (
            first_child.type == "expression_statement"
            and first_child.children[0].type == "string"
        ):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    return ast.literal_eval(get_node_text(first_child.children[0]))
            except (ValueError, SyntaxError):
                return get_node_text(first_child.children[0])
    return None


def find_dict_method_references(
    language: Any,
    root_node: Any,
    language_name: str,
    get_node_text: Callable[[Any], str],
    get_parent_context_fn: Callable[
        [Any, tuple[str, ...]], tuple[str | None, str | None, int | None]
    ],
) -> list[dict[str, Any]]:
    """Detect indirect method calls defined through dictionary mappings.

    Args:
        language: Tree-sitter language object.
        root_node: Tree-sitter root node to inspect.
        language_name: Language name to include in results.
        get_node_text: Callable that decodes nodes to source text.
        get_parent_context_fn: Callable that resolves enclosing contexts.

    Returns:
        Parsed indirect call metadata.
    """
    dict_assignments: dict[str, dict[str, Any]] = {}
    for node, capture_name in execute_query(
        language, PY_QUERIES["dict_method_refs"], root_node
    ):
        if capture_name != "method_ref":
            continue
        dict_node = node.parent
        while dict_node and dict_node.type != "dictionary":
            dict_node = dict_node.parent
        if not dict_node:
            continue

        assignment_node = dict_node.parent
        if not assignment_node or assignment_node.type != "assignment":
            continue

        left_node = assignment_node.child_by_field_name("left")
        if not left_node:
            continue

        var_name = get_node_text(left_node)
        method_ref = get_node_text(node)
        method_name = method_ref.split(".")[-1] if "." in method_ref else method_ref
        if var_name not in dict_assignments:
            dict_assignments[var_name] = {
                "methods": [],
                "context": get_parent_context_fn(
                    assignment_node, ("function_definition", "class_definition")
                ),
            }
        dict_assignments[var_name]["methods"].append(
            {
                "name": method_name,
                "full_name": method_ref,
                "line_number": node.start_point[0] + 1,
            }
        )

    calls: list[dict[str, Any]] = []
    for data in dict_assignments.values():
        context, context_type, context_line = data["context"]
        for method_info in data["methods"]:
            calls.append(
                {
                    "name": method_info["name"],
                    "full_name": method_info["full_name"],
                    "line_number": method_info["line_number"],
                    "args": [],
                    "inferred_obj_type": None,
                    "context": (context, context_type, context_line),
                    "class_context": (None, None),
                    "lang": language_name,
                    "is_dependency": False,
                    "is_indirect_call": True,
                }
            )
    return calls


def pre_scan_python(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Build a class-and-function map for Python files.

    Args:
        files: Python or notebook files to scan.
        parser_wrapper: Wrapper providing parser and language objects.

    Returns:
        Mapping of discovered names to file paths.
    """
    imports_map: dict[str, list[str]] = {}
    query_str = """
        (class_definition name: (identifier) @name)
        (function_definition name: (identifier) @name)
    """

    for path in files:
        temp_py_file = None
        try:
            if path.suffix == ".ipynb":
                temp_py_file = convert_notebook_to_temp_python(path)
                source_to_parse = read_source_text(temp_py_file)
            else:
                source_to_parse = read_source_text(path)

            tree = parser_wrapper.parser.parse(bytes(source_to_parse, "utf8"))
            for capture, _ in execute_query(
                parser_wrapper.language, query_str, tree.root_node
            ):
                name = capture.text.decode("utf-8")
                imports_map.setdefault(name, []).append(str(path.resolve()))
        except Exception as exc:
            warning_logger(f"Tree-sitter pre-scan failed for {path}: {exc}")
        finally:
            if temp_py_file and temp_py_file.exists():
                os.remove(temp_py_file)

    return imports_map
