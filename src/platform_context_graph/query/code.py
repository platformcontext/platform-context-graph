"""Portable code-query helpers shared by the HTTP API and MCP surfaces."""

from __future__ import annotations

from typing import Any, Literal, Sequence

from ..observability import trace_query
from .code_support import (
    LEGACY_DEFAULT_EDIT_DISTANCE,
    QUERY_TYPE_ALIASES,
    get_code_finder,
    legacy_repo_path,
    normalize_module_dependency_result,
    portable_result,
    resolve_query_scope,
    resolve_repo_metadata,
)

__all__ = [
    "search_code",
    "get_code_relationships",
    "find_dead_code",
    "get_complexity",
]
def search_code(
    database: Any,
    *,
    query: str,
    repo_id: str | None = None,
    scope: Literal["repo", "workspace", "ecosystem", "auto"] | str = "auto",
    exact: bool = False,
    limit: int = 10,
    edit_distance: int | None = None,
) -> dict[str, Any]:
    """Search code symbols and related matches.

    Args:
        database: Database manager or code-finder-compatible object.
        query: Search query text.
        repo_id: Optional canonical repository identifier used to scope search.
        scope: Search scope mode. ``auto`` uses ``repo_id`` when present.
        exact: Whether to disable fuzzy search.
        limit: Maximum ranked results to return.
        edit_distance: Optional fuzzy-search edit distance override.

    Returns:
        Search results with portable repository-relative file references.
    """
    with trace_query("search_code"):
        finder = get_code_finder(database, "find_related_code")
        scope_repo_id = resolve_query_scope(repo_id=repo_id, scope=scope)
        repo_path = legacy_repo_path(finder, scope_repo_id)
        repo_metadata = (
            resolve_repo_metadata(finder, scope_repo_id)
            if scope_repo_id is not None
            else None
        )

        fuzzy_search = not exact
        effective_edit_distance = LEGACY_DEFAULT_EDIT_DISTANCE
        if edit_distance is not None:
            effective_edit_distance = edit_distance

        results = finder.find_related_code(
            query,
            fuzzy_search,
            effective_edit_distance,
            repo_path=repo_path,
        )
        if limit >= 0 and "ranked_results" in results:
            results = dict(results)
            repository_cache: dict[str, Any] = {}
            results["ranked_results"] = [
                portable_result(
                    item,
                    repo_metadata,
                    database=finder,
                    repository_cache=repository_cache,
                )
                for item in list(results["ranked_results"])[:limit]
            ]
        return results


def get_code_relationships(
    database: Any,
    *,
    query_type: str,
    target: str,
    context: str | None = None,
    repo_id: str | None = None,
    scope: Literal["repo", "workspace", "ecosystem", "auto"] | str = "auto",
) -> dict[str, Any]:
    """Fetch code relationship data for a target symbol.

    Args:
        database: Database manager or code-finder-compatible object.
        query_type: Relationship query type.
        target: Symbol or entity name to inspect.
        context: Optional contextual filter such as a file path.
        repo_id: Optional canonical repository identifier used to scope the query.
        scope: Query scope mode. ``auto`` uses ``repo_id`` when present.

    Returns:
        Relationship result shaped with portable path fields.
    """
    with trace_query("code_relationships"):
        finder = get_code_finder(database, "analyze_code_relationships")
        scope_repo_id = resolve_query_scope(repo_id=repo_id, scope=scope)
        normalized_query_type = QUERY_TYPE_ALIASES.get(
            query_type.lower().strip(), query_type
        )
        result = finder.analyze_code_relationships(
            normalized_query_type,
            target,
            context,
            repo_path=legacy_repo_path(finder, scope_repo_id),
        )
        portable_query_result = portable_result(
            result,
            (
                resolve_repo_metadata(finder, scope_repo_id)
                if scope_repo_id is not None
                else None
            ),
            database=finder,
        )
        if normalized_query_type in {"module_deps", "module_dependencies"}:
            portable_query_result = normalize_module_dependency_result(
                portable_query_result
            )
        return portable_query_result


def find_dead_code(
    database: Any,
    *,
    repo_id: str | None = None,
    scope: Literal["repo", "workspace", "ecosystem", "auto"] | str = "auto",
    exclude_decorated_with: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Find potentially unused code within an optional repository scope."""
    with trace_query("dead_code"):
        finder = get_code_finder(database, "find_dead_code")
        scope_repo_id = resolve_query_scope(repo_id=repo_id, scope=scope)
        return portable_result(
            finder.find_dead_code(
                exclude_decorated_with=list(exclude_decorated_with or []),
                repo_path=legacy_repo_path(finder, scope_repo_id),
            ),
            (
                resolve_repo_metadata(finder, scope_repo_id)
                if scope_repo_id is not None
                else None
            ),
            database=finder,
        )


def get_complexity(
    database: Any,
    *,
    mode: str = "top",
    limit: int = 10,
    function_name: str | None = None,
    path: str | None = None,
    repo_id: str | None = None,
    scope: Literal["repo", "workspace", "ecosystem", "auto"] | str = "auto",
) -> dict[str, Any] | list[dict[str, Any]]:
    """Return code complexity summaries or a single function's complexity.

    Args:
        database: Database manager or code-finder-compatible object.
        mode: Query mode, such as ``top`` or ``function``.
        limit: Maximum number of ranked functions to return in ``top`` mode.
        function_name: Function name required for ``function`` mode.
        path: Optional path filter for function mode.
        repo_id: Optional canonical repository identifier used to scope the query.
        scope: Query scope mode. ``auto`` uses ``repo_id`` when present.

    Returns:
        Ranked complexity results or a single complexity mapping.

    Raises:
        ValueError: If the requested mode is unsupported or missing inputs.
    """
    with trace_query("complexity"):
        finder = get_code_finder(
            database, "find_most_complex_functions", "get_cyclomatic_complexity"
        )
        scope_repo_id = resolve_query_scope(repo_id=repo_id, scope=scope)
        repo_path = legacy_repo_path(finder, scope_repo_id)
        repo_metadata = (
            resolve_repo_metadata(finder, scope_repo_id)
            if scope_repo_id is not None
            else None
        )
        normalized_mode = mode.lower().strip()

        if normalized_mode in {"top", "find_complexity"}:
            return portable_result(
                finder.find_most_complex_functions(limit, repo_path=repo_path),
                repo_metadata,
                database=finder,
            )

        if normalized_mode in {"function", "single", "calculate"}:
            if not function_name:
                raise ValueError(
                    "function_name is required for function complexity queries"
                )
            return portable_result(
                finder.get_cyclomatic_complexity(
                    function_name, path, repo_path=repo_path
                ),
                repo_metadata,
                database=finder,
            )

        raise ValueError(f"Unsupported complexity mode: {mode}")
