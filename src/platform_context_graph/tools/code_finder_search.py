"""Search-oriented helpers for `CodeFinder` database lookups."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

logger = logging.getLogger(__name__)
_LUCENE_SPECIAL_CHARS_RE = re.compile(r'([+\-!(){}\[\]^"~*?:\\/])')


def _build_exact_name_query(
    label: Literal["Class", "Function"], repo_path: str | None
) -> str:
    """Build the exact-match query for classes or functions.

    Args:
        label: Node label to query.
        repo_path: Optional repository prefix filter.

    Returns:
        A Cypher query string.
    """
    return f"""
        MATCH (node:{label} {{name: $name}})
        {"WHERE node.path STARTS WITH $repo_path" if repo_path else ""}
        RETURN node.name as name, node.path as path, node.line_number as line_number,
               node.source as source, node.docstring as docstring, node[$is_dependency_key] as is_dependency
        LIMIT 20
    """


def _annotate_search_results(
    items: list[dict[str, Any]],
    *,
    search_type: str,
    non_dependency_score: float,
    dependency_score: float,
) -> list[dict[str, Any]]:
    """Annotate search results with ranking metadata in place.

    Args:
        items: Results to annotate.
        search_type: Search category label.
        non_dependency_score: Score for project-owned code.
        dependency_score: Score for dependency code.

    Returns:
        The same result dictionaries after annotation.
    """
    for item in items:
        item["search_type"] = search_type
        item["relevance_score"] = (
            dependency_score if item["is_dependency"] else non_dependency_score
        )
    return items


def _escape_lucene_term(term: str) -> str:
    """Escape Lucene special characters in a single fulltext-search term."""
    return _LUCENE_SPECIAL_CHARS_RE.sub(r"\\\1", term)


class CodeFinderSearchMixin:
    """Provide search-related methods for `CodeFinder`."""

    def format_query(
        self,
        find_by: Literal["Class", "Function"],
        fuzzy_search: bool,
        repo_path: str | None = None,
    ) -> str:
        """Format a name search query for the active database backend.

        Args:
            find_by: Node label to search.
            fuzzy_search: Whether the caller requested fuzzy search behavior.
            repo_path: Optional repository prefix filter.

        Returns:
            A backend-specific Cypher query string.
        """
        repo_filter = "AND node.path STARTS WITH $repo_path" if repo_path else ""
        if self._is_falkordb:
            name_filter = "toLower(node.name) CONTAINS toLower($search_term)"
            return f"""
                MATCH (node:{find_by})
                WHERE {name_filter} {repo_filter}
                RETURN node.name as name, node.path as path, node.line_number as line_number,
                    node.source as source, node.docstring as docstring, node[$is_dependency_key] as is_dependency
                ORDER BY coalesce(node[$is_dependency_key], false) ASC, node.name
                LIMIT 20
            """
        return f"""
            CALL db.index.fulltext.queryNodes("code_search_index", $search_term) YIELD node, score
                WITH node, score
                WHERE node:{find_by} {'AND node.name CONTAINS $search_term' if not fuzzy_search else ''} {repo_filter}
                RETURN node.name as name, node.path as path, node.line_number as line_number,
                    node.source as source, node.docstring as docstring, node[$is_dependency_key] as is_dependency
                ORDER BY score DESC
                LIMIT 20
            """

    def find_by_function_name(
        self, search_term: str, fuzzy_search: bool, repo_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Find functions whose names match the supplied search term.

        Args:
            search_term: Query string to match.
            fuzzy_search: Whether fuzzy search should be used.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching function rows.
        """
        with self.driver.session() as session:
            if not fuzzy_search:
                result = session.run(
                    _build_exact_name_query("Function", repo_path),
                    name=search_term,
                    repo_path=repo_path,
                    is_dependency_key="is_dependency",
                )
                return result.data()

            formatted_search_term = (
                search_term if self._is_falkordb else f"name:{search_term}"
            )
            result = session.run(
                self.format_query("Function", fuzzy_search, repo_path),
                search_term=formatted_search_term,
                repo_path=repo_path,
                is_dependency_key="is_dependency",
            )
            return result.data()

    def find_by_class_name(
        self, search_term: str, fuzzy_search: bool, repo_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Find classes whose names match the supplied search term.

        Args:
            search_term: Query string to match.
            fuzzy_search: Whether fuzzy search should be used.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching class rows.
        """
        with self.driver.session() as session:
            if not fuzzy_search:
                result = session.run(
                    _build_exact_name_query("Class", repo_path),
                    name=search_term,
                    repo_path=repo_path,
                    is_dependency_key="is_dependency",
                )
                return result.data()

            formatted_search_term = (
                search_term if self._is_falkordb else f"name:{search_term}"
            )
            result = session.run(
                self.format_query("Class", fuzzy_search, repo_path),
                search_term=formatted_search_term,
                repo_path=repo_path,
                is_dependency_key="is_dependency",
            )
            return result.data()

    def find_by_variable_name(
        self, search_term: str, repo_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Find variables whose names contain the supplied search term.

        Args:
            search_term: Query string to match.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching variable rows.
        """
        with self.driver.session() as session:
            result = session.run(
                f"""
                MATCH (v:Variable)
                WHERE v.name CONTAINS $search_term {"AND v.path STARTS WITH $repo_path" if repo_path else ""}
                RETURN v.name as name, v.path as path, v.line_number as line_number,
                       v.value as value, v.context as context, v[$is_dependency_key] as is_dependency
                ORDER BY coalesce(v[$is_dependency_key], false) ASC, v.name
                LIMIT 20
            """,
                search_term=search_term,
                repo_path=repo_path,
                is_dependency_key="is_dependency",
            )
            return result.data()

    def find_by_content(
        self, search_term: str, repo_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Find code whose indexed content matches the supplied query.

        Args:
            search_term: Query string to match.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching code rows.
        """
        self._search_warnings = []
        if self._is_falkordb:
            return self._find_by_content_falkordb(search_term, repo_path)

        with self.driver.session() as session:
            result = session.run(
                f"""
                CALL db.index.fulltext.queryNodes("code_search_index", $search_term) YIELD node, score
                WITH node, score
                WHERE (node:Function OR node:Class OR node:Variable) {"AND node.path STARTS WITH $repo_path" if repo_path else ""}
                MATCH (node)<-[:CONTAINS]-(f:File)
                RETURN
                    CASE
                        WHEN node:Function THEN 'function'
                        WHEN node:Class THEN 'class'
                        ELSE 'variable'
                    END as type,
                    node.name as name, f.path as path,
                    node.line_number as line_number, node.source as source,
                    node.docstring as docstring, node[$is_dependency_key] as is_dependency
                ORDER BY score DESC
                LIMIT 20
            """,
                search_term=search_term,
                repo_path=repo_path,
                is_dependency_key="is_dependency",
            )
            return result.data()

    def _find_by_content_falkordb(
        self, search_term: str, repo_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Find content matches using FalkorDB-safe substring filters.

        Args:
            search_term: Query string to match.
            repo_path: Optional repository prefix filter.

        Returns:
            Matching code rows limited to the first twenty results.
        """
        all_results: list[dict[str, Any]] = []
        with self.driver.session() as session:
            repo_filter = "AND node.path STARTS WITH $repo_path" if repo_path else ""
            for label, type_name in [("Function", "function"), ("Class", "class")]:
                try:
                    result = session.run(
                        f"""
                        MATCH (node:{label})
                        WHERE (toLower(node.name) CONTAINS toLower($search_term)
                            OR (node.source IS NOT NULL AND toLower(node.source) CONTAINS toLower($search_term))
                            OR (node.docstring IS NOT NULL AND toLower(node.docstring) CONTAINS toLower($search_term)))
                            {repo_filter}
                        RETURN
                            '{type_name}' as type,
                            node.name as name, node.path as path,
                            node.line_number as line_number, node.source as source,
                            node.docstring as docstring, node[$is_dependency_key] as is_dependency
                        ORDER BY coalesce(node[$is_dependency_key], false) ASC, node.name
                        LIMIT 20
                    """,
                        search_term=search_term,
                        repo_path=repo_path,
                        is_dependency_key="is_dependency",
                    )
                    all_results.extend(result.data())
                except Exception:
                    warning_message = (
                        f"FalkorDB content query failed for label {label}; "
                        "returning partial results"
                    )
                    self._search_warnings.append(warning_message)
                    logger.warning(warning_message, exc_info=True)
        return all_results[:20]

    def find_by_module_name(self, search_term: str) -> list[dict[str, Any]]:
        """Find modules whose names contain the supplied search term.

        Args:
            search_term: Query string to match.

        Returns:
            Matching module rows.
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (m:Module)
                WHERE m.name CONTAINS $search_term
                RETURN m.name as name, m.lang as lang
                ORDER BY m.name
                LIMIT 20
            """,
                search_term=search_term,
            )
            return result.data()

    def find_imports(self, search_term: str) -> list[dict[str, Any]]:
        """Find imports whose alias or imported name matches the query.

        Args:
            search_term: Alias or imported symbol name to match.

        Returns:
            Matching import rows.
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (f:File)-[r:IMPORTS]->(m:Module)
                WHERE r.alias = $search_term OR r.imported_name = $search_term
                RETURN
                    r.alias as alias,
                    r.imported_name as imported_name,
                    m.name as module_name,
                    f.path as path,
                    r.line_number as line_number
                ORDER BY f.path
                LIMIT 20
            """,
                search_term=search_term,
            )
            return result.data()

    def find_related_code(
        self,
        user_query: str,
        fuzzy_search: bool,
        edit_distance: int,
        repo_path: str | None = None,
    ) -> dict[str, Any]:
        """Find code related to a query using several search strategies.

        Args:
            user_query: Original query text.
            fuzzy_search: Whether fuzzy search should be used.
            edit_distance: Requested Lucene-style edit distance.
            repo_path: Optional repository prefix filter.

        Returns:
            Combined and ranked search results.
        """
        if fuzzy_search and self._is_falkordb:
            logger.debug(
                "FalkorDB backend: ignoring fuzzy edit-distance normalisation; "
                "using plain CONTAINS search."
            )
            fuzzy_search = False

        if fuzzy_search:
            user_query_normalized = " ".join(
                f"{_escape_lucene_term(token)}~{edit_distance}"
                for token in user_query.split(" ")
                if token
            )
        elif not self._is_falkordb:
            user_query_normalized = " ".join(
                _escape_lucene_term(token) for token in user_query.split(" ") if token
            )
        else:
            user_query_normalized = user_query

        results: dict[str, Any] = {
            "query": user_query_normalized,
            "functions_by_name": self.find_by_function_name(
                user_query_normalized, fuzzy_search, repo_path
            ),
            "classes_by_name": self.find_by_class_name(
                user_query_normalized, fuzzy_search, repo_path
            ),
            "variables_by_name": self.find_by_variable_name(user_query, repo_path),
            "content_matches": self.find_by_content(user_query_normalized, repo_path),
        }

        ranked_results: list[dict[str, Any]] = []
        ranked_results.extend(
            _annotate_search_results(
                results["functions_by_name"],
                search_type="function_name",
                non_dependency_score=0.9,
                dependency_score=0.7,
            )
        )
        ranked_results.extend(
            _annotate_search_results(
                results["classes_by_name"],
                search_type="class_name",
                non_dependency_score=0.8,
                dependency_score=0.6,
            )
        )
        ranked_results.extend(
            _annotate_search_results(
                results["variables_by_name"],
                search_type="variable_name",
                non_dependency_score=0.7,
                dependency_score=0.5,
            )
        )
        ranked_results.extend(
            _annotate_search_results(
                results["content_matches"],
                search_type="content",
                non_dependency_score=0.6,
                dependency_score=0.4,
            )
        )
        ranked_results.sort(key=lambda item: item["relevance_score"], reverse=True)

        if self._search_warnings:
            results["warnings"] = list(self._search_warnings)
        results["ranked_results"] = ranked_results[:15]
        results["total_matches"] = len(ranked_results)
        return results
