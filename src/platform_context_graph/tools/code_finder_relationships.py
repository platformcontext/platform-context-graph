"""Relationship-oriented helpers for `CodeFinder` graph traversal queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class CodeFinderRelationshipsMixin:
    """Provide relationship and structure queries for `CodeFinder`."""

    def find_functions_by_argument(
        self,
        argument_name: str,
        path: str | None = None,
        repo_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find functions that declare a specific argument name.

        Args:
            argument_name: Parameter name to match.
            path: Optional exact file path filter.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching function rows.
        """
        with self.driver.session() as session:
            repo_filter = "AND f.path STARTS WITH $repo_path" if repo_path else ""
            if path:
                query = f"""
                    MATCH (f:Function)-[:HAS_PARAMETER]->(p:Parameter)
                    WHERE p.name = $argument_name AND f.path = $path {repo_filter}
                    RETURN f.name AS function_name, f.path AS path, f.line_number AS line_number,
                           f.docstring AS docstring, f.is_dependency AS is_dependency
                    ORDER BY f.is_dependency ASC, f.path, f.line_number
                    LIMIT 20
                """
                result = session.run(
                    query, argument_name=argument_name, path=path, repo_path=repo_path
                )
            else:
                query = f"""
                    MATCH (f:Function)-[:HAS_PARAMETER]->(p:Parameter)
                    WHERE p.name = $argument_name {repo_filter}
                    RETURN f.name AS function_name, f.path AS path, f.line_number AS line_number,
                           f.docstring AS docstring, f.is_dependency AS is_dependency
                    ORDER BY f.is_dependency ASC, f.path, f.line_number
                    LIMIT 20
                """
                result = session.run(
                    query, argument_name=argument_name, repo_path=repo_path
                )
            return result.data()

    def find_functions_by_decorator(
        self,
        decorator_name: str,
        path: str | None = None,
        repo_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find functions that are decorated with the supplied decorator.

        Args:
            decorator_name: Decorator name to match.
            path: Optional exact file path filter.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching function rows.
        """
        with self.driver.session() as session:
            repo_filter = "AND f.path STARTS WITH $repo_path" if repo_path else ""
            if path:
                query = f"""
                    MATCH (f:Function)
                    WHERE f.path = $path AND $decorator_name IN f.decorators {repo_filter}
                    RETURN f.name AS function_name, f.path AS path, f.line_number AS line_number,
                           f.docstring AS docstring, f.is_dependency AS is_dependency, f.decorators AS decorators
                    ORDER BY f.is_dependency ASC, f.path, f.line_number
                    LIMIT 20
                """
                result = session.run(
                    query, decorator_name=decorator_name, path=path, repo_path=repo_path
                )
            else:
                query = f"""
                    MATCH (f:Function)
                    WHERE $decorator_name IN f.decorators {repo_filter}
                    RETURN f.name AS function_name, f.path AS path, f.line_number AS line_number,
                           f.docstring AS docstring, f.is_dependency AS is_dependency, f.decorators AS decorators
                    ORDER BY f.is_dependency ASC, f.path, f.line_number
                    LIMIT 20
                """
                result = session.run(
                    query, decorator_name=decorator_name, repo_path=repo_path
                )
            return result.data()

    def who_calls_function(
        self,
        function_name: str,
        path: str | None = None,
        repo_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find functions, classes, or files that call a specific function.

        Args:
            function_name: Target function name.
            path: Optional exact target file path filter.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching caller rows.
        """
        with self.driver.session() as session:
            repo_filter = "AND caller.path STARTS WITH $repo_path" if repo_path else ""
            if path:
                result = session.run(
                    f"""
                    MATCH (caller)-[call:CALLS]->(target:Function {{name: $function_name, path: $path}})
                    WHERE (caller:Function OR caller:Class OR caller:File) {repo_filter}
                    OPTIONAL MATCH (caller_file:File)-[:CONTAINS]->(caller)
                    RETURN DISTINCT
                        caller.name as caller_function,
                        COALESCE(caller.path, caller_file.path) as caller_file_path,
                        caller.line_number as caller_line_number,
                        caller.docstring as caller_docstring,
                        caller.is_dependency as caller_is_dependency,
                        call.line_number as call_line_number,
                        call.args as call_args,
                        call.full_call_name as full_call_name,
                        target.path as target_file_path
                ORDER BY caller_is_dependency ASC, caller_file_path, caller_line_number
                    LIMIT 20
                """,
                    function_name=function_name,
                    path=path,
                    repo_path=repo_path,
                )

                results = result.data()
                if not results:
                    result = session.run(
                        f"""
                        MATCH (caller)-[call:CALLS]->(target:Function {{name: $function_name}})
                        WHERE (caller:Function OR caller:Class OR caller:File) {repo_filter}
                        OPTIONAL MATCH (caller_file:File)-[:CONTAINS]->(caller)
                        RETURN DISTINCT
                            caller.name as caller_function,
                            COALESCE(caller.path, caller_file.path) as caller_file_path,
                            caller.line_number as caller_line_number,
                            caller.docstring as caller_docstring,
                            caller.is_dependency as caller_is_dependency,
                            call.line_number as call_line_number,
                            call.args as call_args,
                            call.full_call_name as full_call_name,
                            target.path as target_file_path
                    ORDER BY caller_is_dependency ASC, caller_file_path, caller_line_number
                        LIMIT 20
                    """,
                        function_name=function_name,
                        repo_path=repo_path,
                    )
                    results = result.data()
            else:
                result = session.run(
                    f"""
                    MATCH (caller:Function)-[call:CALLS]->(target:Function {{name: $function_name}})
                    WHERE 1=1 {repo_filter}
                    OPTIONAL MATCH (caller_file:File)-[:CONTAINS]->(caller)
                    RETURN DISTINCT
                        caller.name as caller_function,
                        caller.path as caller_file_path,
                        caller.line_number as caller_line_number,
                        caller.docstring as caller_docstring,
                        caller.is_dependency as caller_is_dependency,
                        call.line_number as call_line_number,
                        call.args as call_args,
                        call.full_call_name as full_call_name,
                        target.path as target_file_path
                ORDER BY caller_is_dependency ASC, caller_file_path, caller_line_number
                    LIMIT 20
                """,
                    function_name=function_name,
                    repo_path=repo_path,
                )
                results = result.data()

            return results

    def what_does_function_call(
        self,
        function_name: str,
        path: str | None = None,
        repo_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find functions that a specific caller function invokes.

        Args:
            function_name: Caller function name.
            path: Optional exact caller file path filter.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching callee rows.
        """
        with self.driver.session() as session:
            if path:
                absolute_file_path = str(Path(path).resolve())
                result = session.run(
                    f"""
                    MATCH (caller:Function {{name: $function_name, path: $absolute_file_path}})
                    MATCH (caller)-[call:CALLS]->(called:Function)
                    WHERE called.path STARTS WITH $repo_path OR $repo_path IS NULL
                    OPTIONAL MATCH (called_file:File)-[:CONTAINS]->(called)
                    RETURN DISTINCT
                        called.name as called_function,
                        called.path as called_file_path,
                        called.line_number as called_line_number,
                        called.docstring as called_docstring,
                        called.is_dependency as called_is_dependency,
                        call.line_number as call_line_number,
                        call.args as call_args,
                        call.full_call_name as full_call_name
                    ORDER BY called_is_dependency ASC, called_function
                    LIMIT 20
                """,
                    function_name=function_name,
                    absolute_file_path=absolute_file_path,
                    repo_path=repo_path,
                )
            else:
                result = session.run(
                    f"""
                    MATCH (caller:Function {{name: $function_name}})-[call:CALLS]->(called:Function)
                    WHERE called.path STARTS WITH $repo_path OR $repo_path IS NULL
                    OPTIONAL MATCH (called_file:File)-[:CONTAINS]->(called)
                    RETURN DISTINCT
                        called.name as called_function,
                        called.path as called_file_path,
                        called.line_number as called_line_number,
                        called.docstring as called_docstring,
                        called.is_dependency as called_is_dependency,
                        call.line_number as call_line_number,
                        call.args as call_args,
                        call.full_call_name as full_call_name
                    ORDER BY called_is_dependency ASC, called_function
                    LIMIT 20
                """,
                    function_name=function_name,
                    repo_path=repo_path,
                )

            return result.data()

    def who_imports_module(
        self, module_name: str, repo_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Find files that import a given module.

        Args:
            module_name: Module name or full import fragment to match.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching importer rows.
        """
        with self.driver.session() as session:
            repo_filter = "AND file.path STARTS WITH $repo_path" if repo_path else ""
            result = session.run(
                f"""
                MATCH (file:File)-[imp:IMPORTS]->(module:Module)
                WHERE (module.name = $module_name OR module.full_import_name CONTAINS $module_name) {repo_filter}
                OPTIONAL MATCH (repo:Repository)-[:CONTAINS]->(file)
                WITH file, repo, COLLECT({{
                    imported_module: module.name,
                    import_alias: module.alias,
                    full_import_name: module.full_import_name
                }}) AS imports
                RETURN
                    file.name AS file_name,
                    file.path AS path,
                    file.relative_path AS file_relative_path,
                    file.is_dependency AS file_is_dependency,
                    repo.name AS repository_name,
                    imports
                ORDER BY file.is_dependency ASC, file.path
                LIMIT 20
            """,
                module_name=module_name,
                repo_path=repo_path,
            )

            return result.data()

    def who_modifies_variable(
        self, variable_name: str, repo_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Find containers that hold a variable with the supplied name.

        Args:
            variable_name: Variable name to match.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching container rows.
        """
        with self.driver.session() as session:
            repo_filter = (
                "AND container.path STARTS WITH $repo_path" if repo_path else ""
            )
            result = session.run(
                f"""
                MATCH (var:Variable {{name: $variable_name}})
                MATCH (container)-[:CONTAINS]->(var)
                WHERE (container:Function OR container:Class OR container:File) {repo_filter}
                OPTIONAL MATCH (file:File)-[:CONTAINS]->(container)
                RETURN DISTINCT
                    CASE
                        WHEN container:Function THEN container.name
                        WHEN container:Class THEN container.name
                        ELSE 'file_level'
                    END as container_name,
                    CASE
                        WHEN container:Function THEN 'function'
                        WHEN container:Class THEN 'class'
                        ELSE 'file'
                    END as container_type,
                    COALESCE(container.path, file.path) as path,
                    container.line_number as container_line_number,
                    var.line_number as variable_line_number,
                    var.value as variable_value,
                    var.context as variable_context,
                    COALESCE(container.is_dependency, file.is_dependency, false) as is_dependency
                ORDER BY is_dependency ASC, path, variable_line_number
                LIMIT 20
            """,
                variable_name=variable_name,
                repo_path=repo_path,
            )

            return result.data()

    def find_class_hierarchy(
        self,
        class_name: str,
        path: str | None = None,
        repo_path: str | None = None,
    ) -> dict[str, Any]:
        """Find inheritance relationships and methods for a class.

        Args:
            class_name: Class name to match.
            path: Optional exact class file path filter.
            repo_path: Optional repository prefix filter.

        Returns:
            A dictionary containing parents, children, and methods.
        """
        with self.driver.session() as session:
            repo_filter = "AND parent.path STARTS WITH $repo_path" if repo_path else ""
            match_clause = (
                "MATCH (child:Class {name: $class_name, path: $path})"
                if path
                else "MATCH (child:Class {name: $class_name})"
            )

            parents_result = session.run(
                f"""
                {match_clause}
                MATCH (child)-[:INHERITS]->(parent:Class)
                WHERE 1=1 {repo_filter}
                OPTIONAL MATCH (parent_file:File)-[:CONTAINS]->(parent)
                RETURN DISTINCT
                    parent.name as parent_class,
                    parent.path as parent_file_path,
                    parent.line_number as parent_line_number,
                    parent.docstring as parent_docstring,
                    parent.is_dependency as parent_is_dependency
                ORDER BY parent_is_dependency ASC, parent_class
            """,
                class_name=class_name,
                path=path,
                repo_path=repo_path,
            )

            repo_filter_child = (
                "AND grandchild.path STARTS WITH $repo_path" if repo_path else ""
            )
            children_result = session.run(
                f"""
                {match_clause}
                MATCH (grandchild:Class)-[:INHERITS]->(child)
                WHERE 1=1 {repo_filter_child}
                OPTIONAL MATCH (child_file:File)-[:CONTAINS]->(grandchild)
                RETURN DISTINCT
                    grandchild.name as child_class,
                    grandchild.path as child_file_path,
                    grandchild.line_number as child_line_number,
                    grandchild.docstring as child_docstring,
                    grandchild.is_dependency as child_is_dependency
                ORDER BY child_is_dependency ASC, child_class
            """,
                class_name=class_name,
                path=path,
                repo_path=repo_path,
            )

            repo_filter_method = (
                "WHERE method.path STARTS WITH $repo_path" if repo_path else ""
            )
            methods_result = session.run(
                f"""
                {match_clause}
                MATCH (child)-[:CONTAINS]->(method:Function)
                {repo_filter_method}
                RETURN DISTINCT
                    method.name as method_name,
                    method.path as method_file_path,
                    method.line_number as method_line_number,
                    method.args as method_args,
                    method.docstring as method_docstring,
                    method.is_dependency as method_is_dependency
                ORDER BY method_is_dependency ASC, method_line_number
            """,
                class_name=class_name,
                path=path,
                repo_path=repo_path,
            )

            return {
                "class_name": class_name,
                "parent_classes": parents_result.data(),
                "child_classes": children_result.data(),
                "methods": methods_result.data(),
            }

    def find_function_overrides(
        self, function_name: str, repo_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Find implementations of a function across different classes.

        Args:
            function_name: Function name to match.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching override rows.
        """
        with self.driver.session() as session:
            repo_filter = "AND class.path STARTS WITH $repo_path" if repo_path else ""
            result = session.run(
                f"""
                MATCH (class:Class)-[:CONTAINS]->(func:Function {{name: $function_name}})
                WHERE 1=1 {repo_filter}
                OPTIONAL MATCH (file:File)-[:CONTAINS]->(class)
                RETURN DISTINCT
                    class.name as class_name,
                    class.path as class_file_path,
                    func.name as function_name,
                    func.line_number as function_line_number,
                    func.args as function_args,
                    func.docstring as function_docstring,
                    func.is_dependency as is_dependency,
                    file.name as file_name
                ORDER BY is_dependency ASC, class_name
                LIMIT 20
            """,
                function_name=function_name,
                repo_path=repo_path,
            )

            return result.data()
