"""Support helpers for portable code query responses."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from ..repository_identity import build_repo_access, relative_path_from_local
from .code_finder import CodeFinder
from .repositories import (
    _canonical_repository_ref,
    _get_db_manager,
    _repository_metadata_from_row,
    _repository_projection,
    _resolve_repository,
)
from .story_shared import portable_story_value

LEGACY_DEFAULT_EDIT_DISTANCE = 2
QUERY_SCOPES = {"repo", "workspace", "ecosystem", "auto"}
QUERY_TYPE_ALIASES = {
    "callers": "find_callers",
    "callees": "find_callees",
    "imports": "find_importers",
}
REPOSITORY_ROOTS_CACHE_KEY = "__repository_root_candidates__"


def get_code_finder(database: Any, *required_methods: str) -> Any:
    """Return a code-finder-compatible object for the current database."""
    if all(callable(getattr(database, method, None)) for method in required_methods):
        return database

    return CodeFinder(_get_db_manager(database))


def resolve_repo_path(database: Any, repo_id: str | None) -> str | None:
    """Resolve a canonical repository ID to the legacy local-path filter."""
    if repo_id is None or not repo_id.startswith("repository:"):
        return repo_id

    db_manager = _get_db_manager(database)
    with db_manager.get_driver().session() as session:
        repo = _resolve_repository(session, repo_id)
    if not repo:
        return repo_id
    return repo.get("local_path") or repo.get("path") or repo_id


def resolve_repo_metadata(
    database: Any,
    repo_id: str | None,
) -> dict[str, Any] | None:
    """Resolve canonical repository metadata for portable response shaping."""
    if repo_id is None:
        return None

    db_manager = _get_db_manager(database)
    with db_manager.get_driver().session() as session:
        repo = _resolve_repository(session, repo_id)
    if not repo:
        return None
    return _canonical_repository_ref(repo)


def legacy_repo_path(database: Any, repo_id: str | None) -> str | None:
    """Bridge canonical repo IDs to legacy repo_path filters."""
    if repo_id is None:
        return None
    if repo_id.startswith("repository:"):
        return resolve_repo_path(database, repo_id)
    return repo_id


def resolve_query_scope(
    *,
    repo_id: str | None,
    scope: Literal["repo", "workspace", "ecosystem", "auto"] | str = "auto",
) -> str | None:
    """Resolve a scope label into the legacy repo-path filter contract."""
    normalized_scope = scope.lower().strip()
    if normalized_scope not in QUERY_SCOPES:
        raise ValueError(
            f"Unsupported query scope '{scope}'. Expected one of: "
            f"{', '.join(sorted(QUERY_SCOPES))}"
        )
    if normalized_scope == "repo":
        if repo_id is None:
            raise ValueError("Query scope 'repo' requires a repository identifier")
        return repo_id
    if normalized_scope in {"workspace", "ecosystem"}:
        return None
    return repo_id


def portable_path_key(key: str) -> str:
    """Map legacy absolute-path keys to portable relative-path keys."""
    if key == "path":
        return "relative_path"
    if key.endswith("_path"):
        return f"{key[:-5]}_relative_path"
    return key


def result_repository_metadata(
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
        path_candidate = Path(item)
        cache_key = str(path_candidate.resolve()) if path_candidate.is_absolute() else item
        if cache_key not in repository_cache:
            repository_cache[cache_key] = resolve_repo_metadata_for_result_path(
                database,
                cache_key,
                repository_cache=repository_cache,
            )
        if repository_cache[cache_key] is not None:
            return repository_cache[cache_key]
    return None


def repository_root_candidates(
    database: Any,
    *,
    repository_cache: dict[str, Any],
) -> list[tuple[Path, dict[str, Any]]]:
    """Return cached repository roots for workspace result shaping."""
    cached_candidates = repository_cache.get(REPOSITORY_ROOTS_CACHE_KEY)
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
    repository_cache[REPOSITORY_ROOTS_CACHE_KEY] = candidates
    return candidates


def resolve_repo_metadata_for_result_path(
    database: Any,
    candidate_path: str,
    *,
    repository_cache: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve repository metadata for an absolute file-path result."""
    path_candidate = Path(candidate_path)
    if not path_candidate.is_absolute():
        return None

    resolved_path = path_candidate.resolve()
    best_match: dict[str, Any] | None = None
    best_depth = -1
    for repo_root_path, repository_ref in repository_root_candidates(
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


def portable_result(
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
            portable_result(
                item,
                repo,
                database=database,
                repository_cache=repository_cache,
            )
            for item in value
        ]
    if not isinstance(value, dict):
        return value

    resolved_repo = repo or result_repository_metadata(
        value,
        database=database,
        repository_cache=repository_cache,
    )
    portable: dict[str, Any] = {}
    saw_path = False
    for key, item in value.items():
        if isinstance(item, str) and (key == "path" or key.endswith("_path")):
            saw_path = True
            portable[portable_path_key(key)] = relative_path_from_local(
                item,
                None if resolved_repo is None else resolved_repo.get("local_path"),
            )
            continue
        portable[key] = portable_result(
            item,
            resolved_repo,
            database=database,
            repository_cache=repository_cache,
        )

    if resolved_repo is not None and saw_path:
        portable["repo_id"] = resolved_repo["id"]
        portable["repo_access"] = portable_story_value(
            build_repo_access(resolved_repo, interaction_mode="conversational")
        )
    return portable_story_value(portable)


def normalize_module_dependency_result(result: Any) -> Any:
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
