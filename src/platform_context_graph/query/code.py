"""Portable code-query helpers shared by the HTTP API and MCP surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Sequence

from ..observability import trace_query
from ..repository_identity import build_repo_access, relative_path_from_local
from ..tools.code_finder import CodeFinder
from .repositories import (
    _canonical_repository_ref,
    _get_db_manager,
    _repository_metadata_from_row,
    _repository_projection,
    _resolve_repository,
)

__all__ = [
    "search_code",
    "get_code_relationships",
    "find_dead_code",
    "get_complexity",
]
_LEGACY_DEFAULT_EDIT_DISTANCE = 2
_QUERY_SCOPES = {"repo", "workspace", "ecosystem", "auto"}
_QUERY_TYPE_ALIASES = {
    "callers": "find_callers",
    "callees": "find_callees",
    "imports": "find_importers",
}
_REPOSITORY_ROOTS_CACHE_KEY = "__repository_root_candidates__"


def _get_code_finder(database: Any, *required_methods: str) -> Any:
    """Return a code-finder-compatible object for the current database.

    Args:
        database: Database manager or object already exposing code-finder methods.
        *required_methods: Methods that must be present to reuse ``database``
            directly instead of constructing a ``CodeFinder`` wrapper.

    Returns:
        Object implementing the required code-finder query methods.
    """
    if all(callable(getattr(database, method, None)) for method in required_methods):
        return database

    db_manager = _get_db_manager(database)
    return CodeFinder(db_manager)


def _resolve_repo_path(database: Any, repo_id: str | None) -> str | None:
    """Resolve a canonical repository ID to the legacy local path filter."""
    if repo_id is None or not repo_id.startswith("repository:"):
        return repo_id

    db_manager = _get_db_manager(database)
    with db_manager.get_driver().session() as session:
        repo = _resolve_repository(session, repo_id)
    if not repo:
        return repo_id
    return repo.get("local_path") or repo.get("path") or repo_id


def _resolve_repo_metadata(database: Any, repo_id: str | None) -> dict[str, Any] | None:
    """Resolve canonical repository metadata for portable response shaping."""
    if repo_id is None:
        return None

    db_manager = _get_db_manager(database)
    with db_manager.get_driver().session() as session:
        repo = _resolve_repository(session, repo_id)
    if not repo:
        return None
    return _canonical_repository_ref(repo)


def _legacy_repo_path(database: Any, repo_id: str | None) -> str | None:
    """Bridge canonical repo IDs to legacy repo_path filters."""
    if repo_id is None:
        return None
    if repo_id.startswith("repository:"):
        return _resolve_repo_path(database, repo_id)
    return repo_id


def _resolve_query_scope(
    *,
    repo_id: str | None,
    scope: Literal["repo", "workspace", "ecosystem", "auto"] | str = "auto",
) -> str | None:
    """Resolve a scope label into the legacy repo-path filter contract."""

    normalized_scope = scope.lower().strip()
    if normalized_scope not in _QUERY_SCOPES:
        raise ValueError(
            f"Unsupported query scope '{scope}'. Expected one of: "
            f"{', '.join(sorted(_QUERY_SCOPES))}"
        )
    if normalized_scope == "repo":
        if repo_id is None:
            raise ValueError("Query scope 'repo' requires a repository identifier")
        return repo_id
    if normalized_scope in {"workspace", "ecosystem"}:
        return None
    return repo_id


def _portable_path_key(key: str) -> str:
    """Map legacy absolute-path keys to portable relative-path keys."""
    if key == "path":
        return "relative_path"
    if key.endswith("_path"):
        return f"{key[:-5]}_relative_path"
    return key


def _result_repository_metadata(
    value: dict[str, Any],
    *,
    database: Any | None,
    repository_cache: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve repository metadata for a path-bearing result item."""

    if database is None:
        return None

    for key, item in value.items():
        if not isinstance(item, str) or (key != "path" and not key.endswith("_path")):
            continue

        candidate = item
        path_candidate = Path(candidate)
        cache_key = (
            str(path_candidate.resolve()) if path_candidate.is_absolute() else candidate
        )
        if cache_key not in repository_cache:
            repository_cache[cache_key] = _resolve_repo_metadata_for_result_path(
                database,
                cache_key,
                repository_cache=repository_cache,
            )
        if repository_cache[cache_key] is not None:
            return repository_cache[cache_key]
    return None


def _repository_root_candidates(
    database: Any,
    *,
    repository_cache: dict[str, Any],
) -> list[tuple[Path, dict[str, Any]]]:
    """Return cached repository roots for workspace result shaping."""

    cached_candidates = repository_cache.get(_REPOSITORY_ROOTS_CACHE_KEY)
    if cached_candidates is not None:
        return cached_candidates

    db_manager = _get_db_manager(database)
    with db_manager.get_driver().session() as session:
        repositories = session.run(
            f"""
            MATCH (r:Repository)
            RETURN {_repository_projection()}
            ORDER BY r.name
            """,
            local_path_key="local_path",
            remote_url_key="remote_url",
            repo_slug_key="repo_slug",
            has_remote_key="has_remote",
        ).data()

    candidates: list[tuple[Path, dict[str, Any]]] = []
    for repo in repositories:
        metadata = _repository_metadata_from_row(repo)
        repo_root = metadata.get("local_path") or repo.get("path")
        if repo_root is None:
            continue
        candidates.append(
            (
                Path(repo_root).resolve(),
                _canonical_repository_ref(
                    {**repo, **metadata, "id": repo.get("id") or metadata["id"]}
                ),
            )
        )
    repository_cache[_REPOSITORY_ROOTS_CACHE_KEY] = candidates
    return candidates


def _resolve_repo_metadata_for_result_path(
    database: Any,
    candidate_path: str,
    *,
    repository_cache: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve repository metadata for an absolute file path result."""

    path_candidate = Path(candidate_path)
    if not path_candidate.is_absolute():
        return None

    resolved_path = path_candidate.resolve()
    best_match: dict[str, Any] | None = None
    best_depth = -1
    for repo_root_path, repository_ref in _repository_root_candidates(
        database,
        repository_cache=repository_cache,
    ):
        try:
            resolved_path.relative_to(repo_root_path)
        except ValueError:
            continue
        if len(repo_root_path.parts) > best_depth:
            best_match = repository_ref
            best_depth = len(repo_root_path.parts)

    return best_match


def _portable_result(
    value: Any,
    repo: dict[str, Any] | None,
    *,
    database: Any | None = None,
    repository_cache: dict[str, Any] | None = None,
) -> Any:
    """Convert path-bearing query results into portable repo-relative payloads."""
    if repository_cache is None:
        repository_cache = {}

    if isinstance(value, list):
        return [
            _portable_result(
                item,
                repo,
                database=database,
                repository_cache=repository_cache,
            )
            for item in value
        ]
    if not isinstance(value, dict):
        return value

    resolved_repo = repo or _result_repository_metadata(
        value,
        database=database,
        repository_cache=repository_cache,
    )
    portable: dict[str, Any] = {}
    saw_path = False
    for key, item in value.items():
        if isinstance(item, str) and (key == "path" or key.endswith("_path")):
            saw_path = True
            portable[_portable_path_key(key)] = relative_path_from_local(
                item,
                None if resolved_repo is None else resolved_repo.get("local_path"),
            )
            continue
        portable[key] = _portable_result(
            item,
            resolved_repo,
            database=database,
            repository_cache=repository_cache,
        )

    if resolved_repo is not None and saw_path:
        portable["repo_id"] = resolved_repo["id"]
        portable["repo_access"] = build_repo_access(
            resolved_repo, interaction_mode="conversational"
        )
    return portable


def _normalize_module_dependency_result(result: Any) -> Any:
    """Add canonical drill-down aliases to module dependency query results."""

    if not isinstance(result, dict):
        return result

    importers = result.get("importers")
    if not isinstance(importers, list):
        return result

    normalized_importers: list[Any] = []
    for importer in importers:
        if not isinstance(importer, dict):
            normalized_importers.append(importer)
            continue

        normalized_importer = dict(importer)
        if "relative_path" not in normalized_importer:
            relative_path = normalized_importer.get("importer_file_relative_path")
            if isinstance(relative_path, str):
                normalized_importer["relative_path"] = relative_path
            else:
                path_value = normalized_importer.get("importer_file_path")
                if isinstance(path_value, str):
                    normalized_importer["relative_path"] = path_value
        normalized_importers.append(normalized_importer)

    return {**result, "importers": normalized_importers}


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
        finder = _get_code_finder(database, "find_related_code")
        scope_repo_id = _resolve_query_scope(repo_id=repo_id, scope=scope)
        repo_path = _legacy_repo_path(finder, scope_repo_id)
        repo_metadata = (
            _resolve_repo_metadata(finder, scope_repo_id)
            if scope_repo_id is not None
            else None
        )

        fuzzy_search = not exact
        effective_edit_distance = _LEGACY_DEFAULT_EDIT_DISTANCE
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
                _portable_result(
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
        finder = _get_code_finder(database, "analyze_code_relationships")
        scope_repo_id = _resolve_query_scope(repo_id=repo_id, scope=scope)
        normalized_query_type = _QUERY_TYPE_ALIASES.get(
            query_type.lower().strip(), query_type
        )
        result = finder.analyze_code_relationships(
            normalized_query_type,
            target,
            context,
            repo_path=_legacy_repo_path(finder, scope_repo_id),
        )
        portable_result = _portable_result(
            result,
            (
                _resolve_repo_metadata(finder, scope_repo_id)
                if scope_repo_id is not None
                else None
            ),
            database=finder,
        )
        if normalized_query_type in {"module_deps", "module_dependencies"}:
            portable_result = _normalize_module_dependency_result(portable_result)
        return portable_result


def find_dead_code(
    database: Any,
    *,
    repo_id: str | None = None,
    scope: Literal["repo", "workspace", "ecosystem", "auto"] | str = "auto",
    exclude_decorated_with: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Find potentially unused code within an optional repository scope."""
    with trace_query("dead_code"):
        finder = _get_code_finder(database, "find_dead_code")
        scope_repo_id = _resolve_query_scope(repo_id=repo_id, scope=scope)
        return _portable_result(
            finder.find_dead_code(
                exclude_decorated_with=list(exclude_decorated_with or []),
                repo_path=_legacy_repo_path(finder, scope_repo_id),
            ),
            (
                _resolve_repo_metadata(finder, scope_repo_id)
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
        finder = _get_code_finder(
            database, "find_most_complex_functions", "get_cyclomatic_complexity"
        )
        scope_repo_id = _resolve_query_scope(repo_id=repo_id, scope=scope)
        repo_path = _legacy_repo_path(finder, scope_repo_id)
        repo_metadata = (
            _resolve_repo_metadata(finder, scope_repo_id)
            if scope_repo_id is not None
            else None
        )
        normalized_mode = mode.lower().strip()

        if normalized_mode in {"top", "find_complexity"}:
            return _portable_result(
                finder.find_most_complex_functions(limit, repo_path=repo_path),
                repo_metadata,
                database=finder,
            )

        if normalized_mode in {"function", "single", "calculate"}:
            if not function_name:
                raise ValueError(
                    "function_name is required for function complexity queries"
                )
            return _portable_result(
                finder.get_cyclomatic_complexity(
                    function_name, path, repo_path=repo_path
                ),
                repo_metadata,
                database=finder,
            )

        raise ValueError(f"Unsupported complexity mode: {mode}")
