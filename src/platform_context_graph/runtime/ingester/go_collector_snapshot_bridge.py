"""Narrowed snapshot bridge for the Go ``collector-git`` runtime."""

from __future__ import annotations

import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from platform_context_graph.content.ingest import prepare_content_entries
from platform_context_graph.repository_identity import repository_metadata

from .config import RepoSyncConfig
from .go_collector_bridge import (
    _BridgeBuilder,
    _default_build_parser_registry,
    _default_git_remote_for_path,
    _default_parse_repository_snapshot_async,
    _default_pathspec_module,
    _default_resolve_repository_file_sets,
    _default_run_repo_sync_cycle,
    _selected_repositories_for_cycle,
    _snapshot_for_repository,
)


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


def collect_snapshot_batch(
    config: RepoSyncConfig,
    *,
    run_repo_sync_cycle_fn: Callable[..., object] | None = None,
    resolve_repository_file_sets_fn: Callable[..., dict[Path, list[Path]]] | None = None,
    parse_repository_snapshot_async_fn: Callable[..., Any] | None = None,
    build_parser_registry_fn: Callable[..., dict[str, Any]] | None = None,
    git_remote_for_path_fn: Callable[[Path], str | None] = _default_git_remote_for_path,
    utc_now_fn: Callable[[], datetime],
    pathspec_module: object | None = None,
) -> dict[str, Any]:
    """Collect one narrowed snapshot batch in the JSON contract expected by Go."""

    run_repo_sync_cycle_fn = run_repo_sync_cycle_fn or _default_run_repo_sync_cycle
    resolve_repository_file_sets_fn = (
        resolve_repository_file_sets_fn or _default_resolve_repository_file_sets
    )
    parse_repository_snapshot_async_fn = (
        parse_repository_snapshot_async_fn or _default_parse_repository_snapshot_async
    )
    build_parser_registry_fn = (
        build_parser_registry_fn or _default_build_parser_registry
    )

    selected_repositories = _selected_repositories_for_cycle(
        config,
        run_repo_sync_cycle_fn=run_repo_sync_cycle_fn,
    )
    if not selected_repositories:
        return {"observed_at": utc_now_fn().isoformat(), "collected": []}
    pathspec_module = pathspec_module or _default_pathspec_module()

    builder = _BridgeBuilder(parsers=build_parser_registry_fn(None))
    repository_file_sets = resolve_repository_file_sets_fn(
        builder,
        config.repos_dir,
        selected_repositories=selected_repositories,
        pathspec_module=pathspec_module,
    )

    observed_at = utc_now_fn()
    collected: list[dict[str, Any]] = []
    for repo_path in selected_repositories:
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
        repo_metadata = repository_metadata(
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

        collected.append(
            {
                "repo_path": str(resolved_repo_path),
                "remote_url": git_remote_for_path_fn(repo_path),
                "file_count": snapshot.file_count,
                "file_data": _sanitize_for_json(snapshot.file_data),
                "content_files": content_files,
                "content_entities": content_entities,
            }
        )

    return {
        "observed_at": observed_at.isoformat(),
        "collected": collected,
    }


def main() -> int:
    """Run one repo-sync cycle and print the narrowed snapshot batch as JSON."""

    from platform_context_graph.facts.models.base import utc_now

    config = RepoSyncConfig.from_env(component="collector-git-snapshot-bridge")
    with contextlib.redirect_stdout(sys.stderr):
        batch = collect_snapshot_batch(config, utc_now_fn=utc_now)
    json.dump(
        batch,
        sys.stdout,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
