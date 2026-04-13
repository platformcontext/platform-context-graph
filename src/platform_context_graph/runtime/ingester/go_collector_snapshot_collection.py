"""Shared per-repo snapshot helpers for the Go collector compatibility bridge."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.content.ingest import prepare_content_entries

from .config import RepoSyncConfig


class _BridgeBuilder:
    """Minimal builder surface required by parse and discovery helpers."""

    def __init__(self, parsers: dict[str, Any], job_manager: Any | None = None) -> None:
        self.parsers = parsers
        self.job_manager = job_manager
        self.__post_init__()

    def __post_init__(self) -> None:
        """Attach the ``job_manager`` shape expected by parse helpers."""

        if self.job_manager is None:
            self.job_manager = SimpleNamespace(
                update_job=lambda *_args, **_kwargs: None,
            )

    def _collect_supported_files(self, path: Path) -> list[Path]:
        """Return supported files under one repository root."""

        from platform_context_graph.collectors.git.discovery import collect_supported_files
        from platform_context_graph.cli.config_manager import get_config_value
        from platform_context_graph.observability import get_observability

        return collect_supported_files(
            self,
            path,
            get_config_value_fn=get_config_value,
            get_observability_fn=get_observability,
            os_module=__import__("os"),
        )

    def _pre_scan_for_imports(self, files: list[Path]) -> dict[str, Any]:
        """Return import hints for one repository parse snapshot."""

        from platform_context_graph.parsers.registry import pre_scan_for_imports

        return pre_scan_for_imports(self, files)

    def parse_file(
        self,
        repo_path: Path,
        path: Path,
        is_dependency: bool = False,
    ) -> dict[str, Any]:
        """Parse one file through the shared parser-registry entrypoint."""

        from platform_context_graph.cli.config_manager import get_config_value
        from platform_context_graph.parsers.registry import parse_file
        from platform_context_graph.utils.debug_log import (
            debug_log,
            error_logger,
            warning_logger,
        )

        return parse_file(
            self,
            repo_path,
            path,
            is_dependency,
            get_config_value_fn=get_config_value,
            debug_log_fn=debug_log,
            error_logger_fn=error_logger,
            warning_logger_fn=warning_logger,
        )


def _default_build_parser_registry(_get_config_value: object) -> dict[str, Any]:
    """Load the parser registry lazily."""

    from platform_context_graph.cli.config_manager import get_config_value
    from platform_context_graph.parsers.registry import build_parser_registry

    del _get_config_value
    return build_parser_registry(get_config_value)


def _default_resolve_repository_file_sets(
    builder: _BridgeBuilder,
    workspace: Path,
    *,
    selected_repositories: list[Path],
    pathspec_module: object,
) -> dict[Path, list[Path]]:
    """Load repository file-set resolution lazily."""

    from platform_context_graph.collectors.git.discovery import (
        resolve_repository_file_sets,
    )

    return resolve_repository_file_sets(
        builder,
        workspace,
        selected_repositories=selected_repositories,
        pathspec_module=pathspec_module,
    )


def _default_parse_repository_snapshot_async(*args: object, **kwargs: object) -> Any:
    """Load repository parse execution lazily."""

    from platform_context_graph.collectors.git.parse_execution import (
        parse_repository_snapshot_async,
    )

    return parse_repository_snapshot_async(*args, **kwargs)


def _default_pathspec_module() -> object:
    """Load ``pathspec`` lazily for real repository discovery."""

    import pathspec

    return pathspec


def _default_git_remote_for_path(repo_path: Path) -> str | None:
    """Load repository remote resolution lazily."""

    from platform_context_graph.repository_identity import git_remote_for_path

    return git_remote_for_path(repo_path)


def _default_repository_metadata(**kwargs: object) -> dict[str, Any]:
    """Load repository metadata shaping lazily."""

    from platform_context_graph.repository_identity import (
        repository_metadata as _repository_metadata,
    )

    return _repository_metadata(**kwargs)


def _content_file_json(file_entry: Any) -> dict[str, Any]:
    """Return one JSON-safe content-file transport payload."""

    return {
        "relative_path": file_entry.relative_path,
        "content_body": file_entry.content,
        "content_digest": file_entry.content_hash,
        "language": file_entry.language,
        "artifact_type": file_entry.artifact_type,
        "template_dialect": file_entry.template_dialect,
        "iac_relevant": file_entry.iac_relevant,
        "commit_sha": file_entry.commit_sha,
        "indexed_at": file_entry.indexed_at.isoformat(),
    }


def _content_entity_json(entity_entry: Any) -> dict[str, Any]:
    """Return one JSON-safe content-entity transport payload."""

    return {
        "entity_id": entity_entry.entity_id,
        "relative_path": entity_entry.relative_path,
        "entity_type": entity_entry.entity_type,
        "entity_name": entity_entry.entity_name,
        "start_line": entity_entry.start_line,
        "end_line": entity_entry.end_line,
        "start_byte": entity_entry.start_byte,
        "end_byte": entity_entry.end_byte,
        "language": entity_entry.language,
        "artifact_type": entity_entry.artifact_type,
        "template_dialect": entity_entry.template_dialect,
        "iac_relevant": entity_entry.iac_relevant,
        "source_cache": entity_entry.source_cache,
        "indexed_at": entity_entry.indexed_at.isoformat(),
    }


def _sanitize_for_json(value: Any) -> Any:
    """Recursively convert snapshot payloads into JSON-safe values."""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            key: _sanitize_for_json(nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(item) for item in value]
    return value


def _snapshot_for_repository(
    builder: _BridgeBuilder,
    *,
    repo_path: Path,
    repo_files: list[Path],
    parse_repository_snapshot_async_fn: Callable[..., Any],
) -> RepositoryParseSnapshot:
    """Parse one selected repository into an in-memory snapshot."""

    if not repo_files:
        return RepositoryParseSnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=0,
            imports_map={},
            file_data=[],
        )

    return asyncio.run(
        parse_repository_snapshot_async_fn(
            builder,
            repo_path.resolve(),
            repo_files,
            is_dependency=False,
            job_id=None,
            asyncio_module=asyncio,
            info_logger_fn=lambda *_args, **_kwargs: None,
            component="collector-git-bridge",
            mode="sync",
            source="git",
        )
    )


def collect_repository_snapshot(
    config: RepoSyncConfig,
    *,
    repo_path: Path,
    resolve_repository_file_sets_fn: Callable[..., dict[Path, list[Path]]] | None = None,
    parse_repository_snapshot_async_fn: Callable[..., Any] | None = None,
    build_parser_registry_fn: Callable[..., dict[str, Any]] | None = None,
    git_remote_for_path_fn: Callable[[Path], str | None] = _default_git_remote_for_path,
    utc_now_fn: Callable[[], datetime],
    pathspec_module: object | None = None,
) -> dict[str, Any]:
    """Collect one repository snapshot in the JSON contract expected by Go."""

    resolve_repository_file_sets_fn = (
        resolve_repository_file_sets_fn or _default_resolve_repository_file_sets
    )
    parse_repository_snapshot_async_fn = (
        parse_repository_snapshot_async_fn or _default_parse_repository_snapshot_async
    )
    build_parser_registry_fn = (
        build_parser_registry_fn or _default_build_parser_registry
    )
    git_remote_for_path_fn = git_remote_for_path_fn or _default_git_remote_for_path

    pathspec_module = pathspec_module or _default_pathspec_module()
    builder = _BridgeBuilder(parsers=build_parser_registry_fn(None))
    try:
        repository_file_sets = resolve_repository_file_sets_fn(
            builder,
            config.repos_dir,
            repo_path=repo_path,
            pathspec_module=pathspec_module,
        )
    except TypeError:
        repository_file_sets = resolve_repository_file_sets_fn(
            builder,
            config.repos_dir,
            selected_repositories=[repo_path],
            pathspec_module=pathspec_module,
        )

    observed_at = utc_now_fn()
    resolved_repo_path = repo_path.resolve()
    repo_files = repository_file_sets.get(resolved_repo_path, [])
    snapshot = _snapshot_for_repository(
        builder,
        repo_path=repo_path,
        repo_files=repo_files,
        parse_repository_snapshot_async_fn=parse_repository_snapshot_async_fn,
    )

    content_files: list[dict[str, Any]] = []
    content_entities: list[dict[str, Any]] = []
    repo_metadata = _default_repository_metadata(
        name=repo_path.name,
        local_path=str(resolved_repo_path),
        remote_url=git_remote_for_path_fn(repo_path),
    )
    for file_data in snapshot.file_data:
        file_entry, entity_entries = prepare_content_entries(
            file_data=file_data,
            repository=repo_metadata,
        )
        if file_entry is not None:
            content_files.append(_content_file_json(file_entry))
        content_entities.extend(
            _content_entity_json(entity_entry)
            for entity_entry in entity_entries
        )

    return {
        "observed_at": observed_at.isoformat(),
        "repo_path": str(resolved_repo_path),
        "remote_url": git_remote_for_path_fn(repo_path),
        "file_count": snapshot.file_count,
        "file_data": _sanitize_for_json(snapshot.file_data),
        "content_files": content_files,
        "content_entities": content_entities,
    }
