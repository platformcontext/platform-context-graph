"""Catalog, complexity, and repository listing helpers for `CodeFinder`."""

from __future__ import annotations

from typing import Any


class CodeFinderCatalogAnalysisMixin:
    """Provide catalog and complexity helpers for `CodeFinder`."""

    def find_module_dependencies(
        self, module_name: str, repo_path: str | None = None
    ) -> dict[str, Any]:
        """Find files that import a module and related imported modules.

        Args:
            module_name: Module name to inspect.
            repo_path: Optional repository prefix filter.

        Returns:
            A dictionary describing importers and companion imports.
        """
        with self.driver.session() as session:
            repo_filter = "AND file.path STARTS WITH $repo_path" if repo_path else ""
            importers_result = session.run(
                f"""
                MATCH (file:File)-[imp]->(module:Module {{name: $module_name}})
                WHERE type(imp) = 'IMPORTS' {repo_filter}
                OPTIONAL MATCH (repo:Repository)-[:CONTAINS]->(file)
                RETURN DISTINCT
                    file.path as importer_file_path,
                    imp.line_number as import_line_number,
                    file[$is_dependency_key] as file_is_dependency,
                    repo.name as repository_name
                ORDER BY file_is_dependency ASC, file.path
                LIMIT 50
            """,
                module_name=module_name,
                repo_path=repo_path,
                is_dependency_key="is_dependency",
            )

            imports_result = session.run(
                f"""
                MATCH (file:File)-[target_rel]->(target_module:Module {{name: $module_name}})
                WHERE type(target_rel) = 'IMPORTS'
                MATCH (file)-[imp]->(other_module:Module)
                WHERE type(imp) = 'IMPORTS' AND other_module <> target_module {repo_filter}
                RETURN DISTINCT
                    other_module.name as imported_module,
                    imp.alias as import_alias
                ORDER BY other_module.name
                LIMIT 50
            """,
                module_name=module_name,
                repo_path=repo_path,
            )

            return {
                "module_name": module_name,
                "importers": importers_result.data(),
                "imports": imports_result.data(),
            }

    def find_variable_usage_scope(
        self,
        variable_name: str,
        path: str | None = None,
        repo_path: str | None = None,
    ) -> dict[str, Any]:
        """Find scope and usage information for a variable.

        Args:
            variable_name: Variable name to inspect.
            path: Optional exact or suffix file path filter.
            repo_path: Optional repository prefix filter.

        Returns:
            A dictionary describing matching variable instances.
        """
        with self.driver.session() as session:
            repo_filter = "AND var.path STARTS WITH $repo_path" if repo_path else ""
            if path:
                variable_instances = session.run(
                    f"""
                    MATCH (var:Variable {{name: $variable_name}})
                    WHERE (var.path ENDS WITH $path OR var.path = $path) {repo_filter}
                    OPTIONAL MATCH (container)-[:CONTAINS]->(var)
                    WHERE container:Function OR container:Class OR container:File
                    OPTIONAL MATCH (file:File)-[:CONTAINS]->(var)
                    RETURN DISTINCT
                        var.name as variable_name,
                        var.value as variable_value,
                        var.line_number as line_number,
                        var.context as context,
                        COALESCE(var.path, file.path) as path,
                        CASE
                        WHEN container:Function THEN 'function'
                        WHEN container:Class THEN 'class'
                        ELSE 'module'
                    END as scope_type,
                    CASE
                        WHEN container:Function THEN container.name
                        WHEN container:Class THEN container.name
                        ELSE 'module_level'
                    END as scope_name,
                    var[$is_dependency_key] as is_dependency
                ORDER BY is_dependency ASC, path, line_number
                """,
                    variable_name=variable_name,
                    path=path,
                    repo_path=repo_path,
                    is_dependency_key="is_dependency",
                )
            else:
                variable_instances = session.run(
                    f"""
                    MATCH (var:Variable {{name: $variable_name}})
                    WHERE 1=1 {repo_filter}
                    OPTIONAL MATCH (container)-[:CONTAINS]->(var)
                    WHERE container:Function OR container:Class OR container:File
                    OPTIONAL MATCH (file:File)-[:CONTAINS]->(var)
                    RETURN DISTINCT
                        var.name as variable_name,
                        var.value as variable_value,
                        var.line_number as line_number,
                        var.context as context,
                        COALESCE(var.path, file.path) as path,
                        CASE
                            WHEN container:Function THEN 'function'
                            WHEN container:Class THEN 'class'
                            ELSE 'module'
                        END as scope_type,
                        CASE
                            WHEN container:Function THEN container.name
                            WHEN container:Class THEN container.name
                            ELSE 'module_level'
                        END as scope_name,
                        var[$is_dependency_key] as is_dependency
                    ORDER BY is_dependency ASC, path, line_number
                """,
                    variable_name=variable_name,
                    repo_path=repo_path,
                    is_dependency_key="is_dependency",
                )

            return {
                "variable_name": variable_name,
                "instances": variable_instances.data(),
            }

    def get_cyclomatic_complexity(
        self,
        function_name: str,
        path: str | None = None,
        repo_path: str | None = None,
    ) -> dict[str, Any] | None:
        """Get cyclomatic complexity data for a function.

        Args:
            function_name: Function name to inspect.
            path: Optional exact or suffix file path filter.
            repo_path: Optional repository prefix filter.

        Returns:
            The first matching complexity row, if present.
        """
        with self.driver.session() as session:
            repo_filter = "AND f.path STARTS WITH $repo_path" if repo_path else ""
            if path:
                query = f"""
                    MATCH (f:Function {{name: $function_name}})
                    WHERE (f.path ENDS WITH $path OR f.path = $path) {repo_filter}
                    RETURN f.name as function_name, f.cyclomatic_complexity as complexity,
                           f.path as path, f.line_number as line_number
                """
                result = session.run(
                    query, function_name=function_name, path=path, repo_path=repo_path
                )
            else:
                query = f"""
                    MATCH (f:Function {{name: $function_name}})
                    WHERE 1=1 {repo_filter}
                    RETURN f.name as function_name, f.cyclomatic_complexity as complexity,
                           f.path as path, f.line_number as line_number
                """
                result = session.run(
                    query, function_name=function_name, repo_path=repo_path
                )

            result_data = result.data()
            if result_data:
                return result_data[0]
            return None

    def find_most_complex_functions(
        self, limit: int = 10, repo_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Find functions with the highest cyclomatic complexity values.

        Args:
            limit: Maximum number of functions to return.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching complexity rows.
        """
        with self.driver.session() as session:
            repo_filter = "AND f.path STARTS WITH $repo_path" if repo_path else ""
            query = f"""
                MATCH (f:Function)
                WHERE f.cyclomatic_complexity IS NOT NULL AND coalesce(f[$is_dependency_key], false) = false {repo_filter}
                RETURN f.name as function_name, f.path as path, f.cyclomatic_complexity as complexity, f.line_number as line_number
                ORDER BY f.cyclomatic_complexity DESC
                LIMIT $limit
            """
            result = session.run(
                query,
                limit=limit,
                repo_path=repo_path,
                is_dependency_key="is_dependency",
            )
            return result.data()

    def list_indexed_repositories(self) -> list[dict[str, Any]]:
        """List all repositories present in the graph index.

        Returns:
            Repository rows sorted by repository name.
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (r:Repository)
                RETURN r.name as name,
                       r.path as path,
                       coalesce(r[$is_dependency_key], false) as is_dependency
                ORDER BY r.name
            """,
                is_dependency_key="is_dependency",
            )
            return result.data()
