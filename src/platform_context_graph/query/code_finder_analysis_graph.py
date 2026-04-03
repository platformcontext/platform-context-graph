"""Graph traversal and dead-code helpers for `CodeFinder`."""

from __future__ import annotations

from typing import Any


class CodeFinderGraphAnalysisMixin:
    """Provide graph traversal and dead-code helpers for `CodeFinder`."""

    def find_dead_code(
        self,
        exclude_decorated_with: list[str] | None = None,
        repo_path: str | None = None,
    ) -> dict[str, Any]:
        """Find functions that appear to be unused within the indexed project.

        Args:
            exclude_decorated_with: Decorators that should exclude matches.
            repo_path: Optional repository prefix filter.

        Returns:
            A dictionary describing potentially unused functions.
        """
        if exclude_decorated_with is None:
            exclude_decorated_with = []

        with self.driver.session() as session:
            repo_filter = "AND func.path STARTS WITH $repo_path" if repo_path else ""
            result = session.run(
                f"""
                MATCH (func:Function)
                WHERE coalesce(func[$is_dependency_key], false) = false {repo_filter}
                  AND NOT func.name IN ['main', 'setup', 'run']
                  AND NOT (func.name STARTS WITH '__' AND func.name ENDS WITH '__')
                  AND NOT func.name STARTS WITH '_test'
                  AND NOT func.name STARTS WITH 'test_'
                  AND NOT func.name CONTAINS 'main'
                  AND NOT toLower(func.name) CONTAINS 'application'
                  AND NOT toLower(func.name) CONTAINS 'entry'
                  AND NOT toLower(func.name) CONTAINS 'entrypoint'
                  AND ALL(decorator_name IN $exclude_decorated_with WHERE NOT decorator_name IN func.decorators)
                WITH func
                OPTIONAL MATCH (caller:Function)-[:CALLS]->(func)
                WHERE coalesce(caller[$is_dependency_key], false) = false
                WITH func, count(caller) as caller_count
                WHERE caller_count = 0
                OPTIONAL MATCH (file:File)-[:CONTAINS]->(func)
                RETURN
                    func.name as function_name,
                    func.path as path,
                    func.line_number as line_number,
                    func.docstring as docstring,
                    func.context as context,
                    file.name as file_name
                ORDER BY func.path, func.line_number
                LIMIT 50
            """,
                exclude_decorated_with=exclude_decorated_with,
                repo_path=repo_path,
                is_dependency_key="is_dependency",
            )

            return {
                "potentially_unused_functions": result.data(),
                "note": "These functions might be unused, but could be entry points, callbacks, or called dynamically",
            }

    def find_all_callers(
        self,
        function_name: str,
        path: str | None = None,
        repo_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find direct and indirect callers of a specific function.

        Args:
            function_name: Target function name.
            path: Optional exact target file path filter.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching caller rows.
        """
        with self.driver.session() as session:
            repo_filter = "AND f.path STARTS WITH $repo_path" if repo_path else ""
            if path:
                query = f"""
                    MATCH p = (f:Function)-[:CALLS*]->()
                    WITH f, p, nodes(p) as path_nodes
                    WITH f, path_nodes, list_extract(path_nodes, size(path_nodes)) as target
                    WHERE target.name = $function_name AND target.path = $path {repo_filter}
                    RETURN DISTINCT f.name AS caller_name, f.path AS caller_file_path, f.line_number AS caller_line_number, f[$is_dependency_key] AS caller_is_dependency
                    ORDER BY caller_is_dependency ASC, caller_file_path, caller_line_number
                    LIMIT 50
                """
                result = session.run(
                    query,
                    function_name=function_name,
                    path=path,
                    repo_path=repo_path,
                    is_dependency_key="is_dependency",
                )
            else:
                query = f"""
                    MATCH p = (f:Function)-[:CALLS*]->()
                    WITH f, p, nodes(p) as path_nodes
                    WITH f, path_nodes, list_extract(path_nodes, size(path_nodes)) as target
                    WHERE target.name = $function_name {repo_filter}
                    RETURN DISTINCT f.name AS caller_name, f.path AS caller_file_path, f.line_number AS caller_line_number, f[$is_dependency_key] AS caller_is_dependency
                    ORDER BY caller_is_dependency ASC, caller_file_path, caller_line_number
                    LIMIT 50
                """
                result = session.run(
                    query,
                    function_name=function_name,
                    repo_path=repo_path,
                    is_dependency_key="is_dependency",
                )
            return result.data()

    def find_all_callees(
        self,
        function_name: str,
        path: str | None = None,
        repo_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find direct and indirect callees of a specific function.

        Args:
            function_name: Caller function name.
            path: Optional exact caller file path filter.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching callee rows.
        """
        with self.driver.session() as session:
            repo_filter = "WHERE f.path STARTS WITH $repo_path" if repo_path else ""
            if path:
                query = f"""
                    MATCH (caller:Function {{name: $function_name, path: $path}})
                    MATCH p = (caller)-[:CALLS*]->()
                    WITH p, nodes(p) as path_nodes
                    WITH list_extract(path_nodes, size(path_nodes)) as f
                    {repo_filter}
                    RETURN DISTINCT f.name AS callee_name, f.path AS callee_file_path, f.line_number AS callee_line_number, f[$is_dependency_key] AS callee_is_dependency
                    ORDER BY callee_is_dependency ASC, callee_file_path, callee_line_number
                    LIMIT 50
                """
                result = session.run(
                    query,
                    function_name=function_name,
                    path=path,
                    repo_path=repo_path,
                    is_dependency_key="is_dependency",
                )
            else:
                query = f"""
                    MATCH (caller:Function {{name: $function_name}})
                    MATCH p = (caller)-[:CALLS*]->()
                    WITH p, nodes(p) as path_nodes
                    WITH list_extract(path_nodes, size(path_nodes)) as f
                    {repo_filter}
                    RETURN DISTINCT f.name AS callee_name, f.path AS callee_file_path, f.line_number AS callee_line_number, f[$is_dependency_key] AS callee_is_dependency
                    ORDER BY callee_is_dependency ASC, callee_file_path, callee_line_number
                    LIMIT 50
                """
                result = session.run(
                    query,
                    function_name=function_name,
                    repo_path=repo_path,
                    is_dependency_key="is_dependency",
                )
            return result.data()

    def find_function_call_chain(
        self,
        start_function: str,
        end_function: str,
        max_depth: int = 5,
        start_file: str | None = None,
        end_file: str | None = None,
        repo_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find call chains between two functions.

        Args:
            start_function: Starting function name.
            end_function: Ending function name.
            max_depth: Maximum traversal depth.
            start_file: Optional exact start file path filter.
            end_file: Optional exact end file path filter.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching call-chain rows.
        """
        with self.driver.session() as session:
            start_props = "{name: $start_function" + (
                ", path: $start_file}" if start_file else "}"
            )
            end_props = "{name: $end_function" + (
                ", path: $end_file}" if end_file else "}"
            )
            repo_filter = (
                "WHERE 1=1 AND (start.path IS NULL OR start.path STARTS WITH $repo_path) "
                "AND (end_target.path IS NULL OR end_target.path STARTS WITH $repo_path)"
                if repo_path
                else ""
            )
            query = f"""
                MATCH (start:Function {start_props}), (end_target:Function {end_props})
                {repo_filter}
                WITH start, end_target
                MATCH path = (start)-[:CALLS*1..{max_depth}]->()
                WITH path, end_target, nodes(path) as func_nodes, relationships(path) as call_rels
                WITH path, func_nodes, call_rels, list_extract(func_nodes, size(func_nodes)) as path_end
                WHERE path_end.name = end_target.name AND (end_target.path IS NULL OR path_end.path = end_target.path)
                RETURN
                    [node in func_nodes | {{
                        name: node.name,
                        path: node.path,
                        line_number: node.line_number,
                        is_dependency: node[$is_dependency_key]
                    }}] as function_chain,
                    [rel in call_rels | {{
                        call_line: rel.line_number,
                        args: rel.args,
                        full_call_name: rel.full_call_name
                    }}] as call_details,
                    length(path) as chain_length
                ORDER BY chain_length ASC
                LIMIT 20
            """
            params = {
                "start_function": start_function,
                "end_function": end_function,
                "start_file": start_file,
                "end_file": end_file,
                "repo_path": repo_path,
                "is_dependency_key": "is_dependency",
            }
            result = session.run(query, params)
            return result.data()

    def find_by_type(self, element_type: str, limit: int = 50) -> list[dict[str, Any]]:
        """Find indexed elements by graph node type.

        Args:
            element_type: Type label to search for.
            limit: Maximum number of rows to return.

        Returns:
            Matching node rows.
        """
        type_map = {
            "function": "Function",
            "class": "Class",
            "file": "File",
            "module": "Module",
        }
        label = type_map.get(element_type.lower())
        if not label:
            return []

        with self.driver.session() as session:
            if label == "File":
                query = """
                    MATCH (n:File)
                    RETURN n.name as name, n.path as path, n[$is_dependency_key] as is_dependency
                    ORDER BY n.path
                    LIMIT $limit
                """
            elif label == "Module":
                query = """
                    MATCH (n:Module)
                    RETURN n.name as name, n.name as path, false as is_dependency
                    ORDER BY n.name
                    LIMIT $limit
                """
            else:
                query = f"""
                    MATCH (n:{label})
                    RETURN n.name as name, n.path as path, n.line_number as line_number, n[$is_dependency_key] as is_dependency
                    ORDER BY is_dependency ASC, name
                    LIMIT $limit
                """

            result = session.run(query, limit=limit, is_dependency_key="is_dependency")
            return result.data()
