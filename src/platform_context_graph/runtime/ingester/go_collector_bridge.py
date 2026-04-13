"""Compatibility bridge for the Go ``collector-git`` runtime."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from platform_context_graph.content.ingest import prepare_content_entries
from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.facts.models.base import stable_fact_id, utc_now
from platform_context_graph.indexing.coordinator_facts_support import (
    repository_id_for_path,
    source_snapshot_id,
)

from .config import RepoSyncConfig
from .go_collector_bridge_facts import (
    bridge_generation,
    bridge_scope,
    content_fact,
    content_entity_fact,
    file_fact,
    repository_fact,
    workload_identity_fact,
)
from .go_collector_selection_bridge import _default_run_repo_sync_cycle
from .go_collector_selection_bridge import _selected_repositories_for_cycle
from .go_collector_snapshot_collection import (
    _BridgeBuilder,
    _default_build_parser_registry,
    _default_git_remote_for_path,
    _default_parse_repository_snapshot_async,
    _default_pathspec_module,
    _default_resolve_repository_file_sets,
    _default_repository_metadata,
    _snapshot_for_repository,
)


def _repository_facts(
    *,
    repo_path: Path,
    repo_id: str,
    repo_metadata: dict[str, Any],
    scope_id: str,
    generation_id: str,
    observed_at: datetime,
    snapshot: RepositoryParseSnapshot,
) -> list[dict[str, Any]]:
    """Build all facts for one parsed repository snapshot."""

    content_repo_id = str(repo_metadata["id"])
    facts = [
        repository_fact(
            repo_path=repo_path,
            repo_id=repo_id,
            repo_metadata=repo_metadata,
            scope_id=scope_id,
            generation_id=generation_id,
            observed_at=observed_at,
            parsed_file_count=len(snapshot.file_data),
        )
    ]

    for file_data in snapshot.file_data:
        file_path = Path(str(file_data["path"])).resolve()
        language = str(file_data.get("language") or file_data.get("lang") or "").strip() or None
        file_entry, entity_entries = prepare_content_entries(
            file_data=file_data,
            repository=repo_metadata,
        )
        facts.append(
            file_fact(
                repo_path=repo_path,
                repo_id=repo_id,
                file_path=file_path,
                language=file_entry.language if file_entry is not None else language,
                parsed_file_data=file_data,
                scope_id=scope_id,
                generation_id=generation_id,
                observed_at=observed_at,
            )
        )
        facts.append(
            content_fact(
                repo_path=repo_path,
                repo_id=repo_id,
                file_path=file_path,
                language=file_entry.language if file_entry is not None else language,
                file_entry=file_entry,
                scope_id=scope_id,
                generation_id=generation_id,
                observed_at=observed_at,
            )
        )
        for entity in entity_entries:
            facts.append(
                content_entity_fact(
                    repo_path=repo_path,
                    repo_id=content_repo_id,
                    file_path=file_path,
                    entity=entity,
                    scope_id=scope_id,
                    generation_id=generation_id,
                    observed_at=observed_at,
                )
            )

    facts.append(
        workload_identity_fact(
            repo_path=repo_path,
            repo_id=repo_id,
            scope_id=scope_id,
            generation_id=generation_id,
            observed_at=observed_at,
        )
    )
    return facts


def collect_batch(
    config: RepoSyncConfig,
    *,
    run_repo_sync_cycle_fn: Callable[..., object] | None = None,
    resolve_repository_file_sets_fn: Callable[..., dict[Path, list[Path]]] | None = None,
    parse_repository_snapshot_async_fn: Callable[..., Any] | None = None,
    build_parser_registry_fn: Callable[..., dict[str, Any]] | None = None,
    repository_id_for_path_fn: Callable[[Path], str] = repository_id_for_path,
    source_snapshot_id_fn: Callable[..., str] = source_snapshot_id,
    git_remote_for_path_fn: Callable[[Path], str | None] = _default_git_remote_for_path,
    repository_metadata_fn: Callable[..., dict[str, Any]] = _default_repository_metadata,
    utc_now_fn: Callable[[], datetime] = utc_now,
    pathspec_module: object | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Collect one bridge batch in the JSON contract expected by Go."""

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
        return {"collected": []}
    pathspec_module = pathspec_module or _default_pathspec_module()

    builder = _BridgeBuilder(parsers=build_parser_registry_fn(None))
    repository_file_sets = resolve_repository_file_sets_fn(
        builder,
        config.repos_dir,
        selected_repositories=selected_repositories,
        pathspec_module=pathspec_module,
    )

    observed_at = utc_now_fn()
    source_run_id = stable_fact_id(
        fact_type="GitCollectorBridgeRun",
        identity={
            "component": config.component,
            "selected_repositories": [str(path) for path in selected_repositories],
            "observed_at": observed_at.isoformat(),
        },
    )

    collected: list[dict[str, Any]] = []
    for repo_path in selected_repositories:
        repo_files = repository_file_sets.get(repo_path.resolve(), [])
        snapshot = _snapshot_for_repository(
            builder,
            repo_path=repo_path,
            repo_files=repo_files,
            parse_repository_snapshot_async_fn=parse_repository_snapshot_async_fn,
        )
        repo_metadata = repository_metadata_fn(
            name=repo_path.name,
            local_path=str(repo_path.resolve()),
            remote_url=git_remote_for_path_fn(repo_path),
        )
        repo_id = repository_id_for_path_fn(repo_path)
        scope_value = bridge_scope(repo_id=repo_id, repo_metadata=repo_metadata)
        generation_value = bridge_generation(
            scope_id=str(scope_value["scope_id"]),
            repo_path=repo_path,
            source_run_id=source_run_id,
            observed_at=observed_at,
            source_snapshot_id_fn=source_snapshot_id_fn,
        )
        collected.append(
            {
                "scope": scope_value,
                "generation": generation_value,
                "facts": _repository_facts(
                    repo_path=repo_path,
                    repo_id=repo_id,
                    repo_metadata=repo_metadata,
                    scope_id=str(scope_value["scope_id"]),
                    generation_id=str(generation_value["generation_id"]),
                    observed_at=observed_at,
                    snapshot=snapshot,
                ),
            }
        )

    return {"collected": collected}


def main() -> int:
    """Run one repo-sync cycle and print the bridge batch as JSON."""

    config = RepoSyncConfig.from_env(component="collector-git-bridge")
    json.dump(collect_batch(config), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
