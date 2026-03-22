"""Dispatch helpers for `CodeFinder` relationship analysis entry points."""

from __future__ import annotations

from typing import Any


class CodeFinderDispatchMixin:
    """Provide relationship-analysis dispatch for `CodeFinder`."""

    def analyze_code_relationships(
        self,
        query_type: str,
        target: str,
        context: str | None = None,
        repo_path: str | None = None,
    ) -> dict[str, Any]:
        """Analyze graph relationships for a target based on a query type.

        Args:
            query_type: Requested relationship query type.
            target: Primary query target.
            context: Optional secondary context value.
            repo_path: Optional repository prefix filter.

        Returns:
            A result payload or an error payload.
        """
        query_type = query_type.lower().strip()

        try:
            if query_type == "find_callers":
                results = self.who_calls_function(target, context, repo_path=repo_path)
                return {
                    "query_type": "find_callers",
                    "target": target,
                    "context": context,
                    "results": results,
                    "summary": f"Found {len(results)} functions that call '{target}'",
                }

            elif query_type == "find_callees":
                results = self.what_does_function_call(
                    target, context, repo_path=repo_path
                )
                return {
                    "query_type": "find_callees",
                    "target": target,
                    "context": context,
                    "results": results,
                    "summary": f"Function '{target}' calls {len(results)} other functions",
                }

            elif query_type == "find_importers":
                results = self.who_imports_module(target, repo_path=repo_path)
                return {
                    "query_type": "find_importers",
                    "target": target,
                    "results": results,
                    "summary": f"Found {len(results)} files that import '{target}'",
                }

            elif query_type == "find_functions_by_argument":
                results = self.find_functions_by_argument(
                    target, context, repo_path=repo_path
                )
                return {
                    "query_type": "find_functions_by_argument",
                    "target": target,
                    "context": context,
                    "results": results,
                    "summary": f"Found {len(results)} functions that take '{target}' as an argument",
                }

            elif query_type == "find_functions_by_decorator":
                results = self.find_functions_by_decorator(
                    target, context, repo_path=repo_path
                )
                return {
                    "query_type": "find_functions_by_decorator",
                    "target": target,
                    "context": context,
                    "results": results,
                    "summary": f"Found {len(results)} functions decorated with '{target}'",
                }

            elif query_type in [
                "who_modifies",
                "modifies",
                "mutations",
                "changes",
                "variable_usage",
            ]:
                results = self.who_modifies_variable(target, repo_path=repo_path)
                return {
                    "query_type": "who_modifies",
                    "target": target,
                    "results": results,
                    "summary": f"Found {len(results)} containers that hold variable '{target}'",
                }

            elif query_type in ["class_hierarchy", "inheritance", "extends"]:
                results = self.find_class_hierarchy(
                    target, context, repo_path=repo_path
                )
                return {
                    "query_type": "class_hierarchy",
                    "target": target,
                    "results": results,
                    "summary": f"Class '{target}' has {len(results['parent_classes'])} parents, {len(results['child_classes'])} children, and {len(results['methods'])} methods",
                }

            elif query_type in ["overrides", "implementations", "polymorphism"]:
                results = self.find_function_overrides(target, repo_path=repo_path)
                return {
                    "query_type": "overrides",
                    "target": target,
                    "results": results,
                    "summary": f"Found {len(results)} implementations of function '{target}'",
                }

            elif query_type in ["dead_code", "unused", "unreachable"]:
                results = self.find_dead_code(repo_path=repo_path)
                return {
                    "query_type": "dead_code",
                    "results": results,
                    "summary": f"Found {len(results['potentially_unused_functions'])} potentially unused functions",
                }

            elif query_type == "find_complexity":
                limit = int(context) if context and context.isdigit() else 10
                results = self.find_most_complex_functions(limit, repo_path=repo_path)
                return {
                    "query_type": "find_complexity",
                    "limit": limit,
                    "results": results,
                    "summary": f"Found the top {len(results)} most complex functions",
                }

            elif query_type == "find_all_callers":
                results = self.find_all_callers(target, context, repo_path=repo_path)
                return {
                    "query_type": "find_all_callers",
                    "target": target,
                    "context": context,
                    "results": results,
                    "summary": f"Found {len(results)} direct and indirect callers of '{target}'",
                }

            elif query_type == "find_all_callees":
                results = self.find_all_callees(target, context, repo_path=repo_path)
                return {
                    "query_type": "find_all_callees",
                    "target": target,
                    "context": context,
                    "results": results,
                    "summary": f"Found {len(results)} direct and indirect callees of '{target}'",
                }

            elif query_type in ["call_chain", "path", "chain"]:
                if "->" in target:
                    start_func, end_func = target.split("->", 1)
                    max_depth = int(context) if context and context.isdigit() else 5
                    results = self.find_function_call_chain(
                        start_func.strip(),
                        end_func.strip(),
                        max_depth,
                        repo_path=repo_path,
                    )
                    return {
                        "query_type": "call_chain",
                        "target": target,
                        "results": results,
                        "summary": f"Found {len(results)} call chains from '{start_func.strip()}' to '{end_func.strip()}' (max depth: {max_depth})",
                    }
                else:
                    return {
                        "error": "For call_chain queries, use format 'start_function->end_function'",
                        "example": "main->process_data",
                    }

            elif query_type in ["module_deps", "module_dependencies", "module_usage"]:
                results = self.find_module_dependencies(target, repo_path=repo_path)
                return {
                    "query_type": "module_dependencies",
                    "target": target,
                    "results": results,
                    "summary": f"Module '{target}' is imported by {len(results['imported_by_files'])} files",
                }

            elif query_type in ["variable_scope", "var_scope", "variable_usage_scope"]:
                results = self.find_variable_usage_scope(target, repo_path=repo_path)
                return {
                    "query_type": "variable_scope",
                    "target": target,
                    "results": results,
                    "summary": f"Variable '{target}' has {len(results['instances'])} instances across different scopes",
                }

            else:
                return {
                    "error": f"Unknown query type: {query_type}",
                    "supported_types": [
                        "find_callers",
                        "find_callees",
                        "find_importers",
                        "who_modifies",
                        "class_hierarchy",
                        "overrides",
                        "dead_code",
                        "call_chain",
                        "module_deps",
                        "variable_scope",
                        "find_complexity",
                    ],
                }

        except Exception as exc:
            return {
                "error": f"Error executing relationship query: {str(exc)}",
                "query_type": query_type,
                "target": target,
            }
