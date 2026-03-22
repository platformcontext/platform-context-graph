"""MCP handler functions for code-analysis operations."""

from __future__ import annotations

from typing import Any

from ....query import code as code_queries
from ....tools.code_finder import CodeFinder
from ....utils.debug_log import debug_log


def find_dead_code(code_finder: CodeFinder, **args: Any) -> dict[str, Any]:
    """Tool to find potentially dead code across the entire project."""
    exclude_decorated_with = args.get("exclude_decorated_with", [])
    repo_path = args.get("repo_path")
    try:
        debug_log(f"Finding dead code. repo_path={repo_path}")
        results = code_queries.find_dead_code(
            code_finder,
            repo_path=repo_path,
            exclude_decorated_with=exclude_decorated_with,
        )

        return {"success": True, "query_type": "dead_code", "results": results}
    except Exception as exc:
        debug_log(f"Error finding dead code: {str(exc)}")
        return {"error": f"Failed to find dead code: {str(exc)}"}


def calculate_cyclomatic_complexity(
    code_finder: CodeFinder, **args: Any
) -> dict[str, Any]:
    """Tool to calculate cyclomatic complexity for a given function."""
    function_name = args.get("function_name")
    path = args.get("path")
    repo_path = args.get("repo_path")

    try:
        debug_log(
            f"Calculating cyclomatic complexity for function: {function_name}, repo_path={repo_path}"
        )
        results = code_queries.get_complexity(
            code_finder,
            mode="function",
            function_name=function_name,
            path=path,
            repo_id=repo_path,
        )

        response = {"success": True, "function_name": function_name, "results": results}
        if path:
            response["path"] = path

        return response
    except Exception as exc:
        debug_log(f"Error calculating cyclomatic complexity: {str(exc)}")
        return {"error": f"Failed to calculate cyclomatic complexity: {str(exc)}"}


def find_most_complex_functions(code_finder: CodeFinder, **args: Any) -> dict[str, Any]:
    """Tool to find the most complex functions."""
    limit = args.get("limit", 10)
    repo_path = args.get("repo_path")
    try:
        debug_log(
            f"Finding the top {limit} most complex functions. repo_path={repo_path}"
        )
        results = code_queries.get_complexity(
            code_finder,
            mode="top",
            limit=limit,
            repo_id=repo_path,
        )
        return {"success": True, "limit": limit, "results": results}
    except Exception as exc:
        debug_log(f"Error finding most complex functions: {str(exc)}")
        return {"error": f"Failed to find most complex functions: {str(exc)}"}


def analyze_code_relationships(code_finder: CodeFinder, **args: Any) -> dict[str, Any]:
    """Tool to analyze code relationships."""
    query_type = args.get("query_type")
    target = args.get("target")
    context = args.get("context")
    repo_path = args.get("repo_path")

    if not query_type or not target:
        return {
            "error": "Both 'query_type' and 'target' are required",
            "supported_query_types": [
                "find_callers",
                "find_callees",
                "find_all_callers",
                "find_all_callees",
                "find_importers",
                "who_modifies",
                "class_hierarchy",
                "overrides",
                "dead_code",
                "call_chain",
                "module_deps",
                "variable_scope",
                "find_complexity",
                "find_functions_by_argument",
                "find_functions_by_decorator",
            ],
        }

    try:
        debug_log(
            f"Analyzing relationships: {query_type} for {target}, repo_path={repo_path}"
        )
        results = code_queries.get_code_relationships(
            code_finder,
            query_type=query_type,
            target=target,
            context=context,
            repo_id=repo_path,
        )

        return {
            "success": True,
            "query_type": query_type,
            "target": target,
            "context": context,
            "results": results,
        }

    except Exception as exc:
        debug_log(f"Error analyzing relationships: {str(exc)}")
        return {"error": f"Failed to analyze relationships: {str(exc)}"}


def find_code(code_finder: CodeFinder, **args: Any) -> dict[str, Any]:
    """Tool to find relevant code snippets."""
    query = args.get("query")
    DEFAULT_EDIT_DISTANCE = 2
    DEFAULT_FUZZY_SEARCH = False

    fuzzy_search = args.get("fuzzy_search", DEFAULT_FUZZY_SEARCH)
    edit_distance = args.get("edit_distance", DEFAULT_EDIT_DISTANCE)
    repo_path = args.get("repo_path")

    if not isinstance(query, str) or not query.strip():
        return {"error": "The 'query' argument is required."}

    if fuzzy_search and isinstance(query, str):
        # Assuming minimal normalization is fine here if not method available
        query = query.lower().replace("_", " ").strip()

    try:
        debug_log(
            f"Finding code for query: {query} with fuzzy_search={fuzzy_search}, edit_distance={edit_distance}, repo_path={repo_path}"
        )
        results = code_queries.search_code(
            code_finder,
            query=query,
            repo_id=repo_path,
            exact=not fuzzy_search,
            limit=15,
            edit_distance=edit_distance if fuzzy_search else None,
        )

        return {"success": True, "query": query, "results": results}

    except Exception as exc:
        debug_log(f"Error finding code: {str(exc)}")
        return {"error": f"Failed to find code: {str(exc)}"}
