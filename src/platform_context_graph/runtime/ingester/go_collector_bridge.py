"""Compatibility bridge for the Go ``collector-git`` runtime."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

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
    file_fact,
    repository_fact,
    workload_identity_fact,
)


@dataclass(slots=True)
class _BridgeBuilder:
    """Minimal builder surface required by parse and discovery helpers."""

    parsers: dict[str, Any]
    job_manager: Any | None = None

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
            os_module=os,
        )

    def _pre_scan_for_imports(self, files: list[Path]) -> dict[str, Any]:
        """Return import hints for one repository parse snapshot."""

        from platform_context_graph.parsers.registry import pre_scan_for_imports

        return pre_scan_for_imports(self, files)


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


def _default_run_repo_sync_cycle(*args: object, **kwargs: object) -> Any:
    """Load repo-sync execution lazily."""

    from .sync import run_repo_sync_cycle

    return run_repo_sync_cycle(*args, **kwargs)


def _default_git_remote_for_path(repo_path: Path) -> str | None:
    """Load repository remote resolution lazily."""

    from platform_context_graph.repository_identity import git_remote_for_path

    return git_remote_for_path(repo_path)


def _default_repository_metadata(**kwargs: object) -> dict[str, Any]:
    """Load repository metadata shaping lazily."""

    from platform_context_graph.repository_identity import repository_metadata

    return repository_metadata(**kwargs)


def _default_pathspec_module() -> object:
    """Load ``pathspec`` lazily for real repository discovery."""

    import pathspec

    return pathspec


def _selected_repositories_for_cycle(
    config: RepoSyncConfig,
    *,
    run_repo_sync_cycle_fn: Callable[..., object],
) -> list[Path]:
    """Return the repositories selected by one repo-sync cycle."""

    selected: list[Path] = []

    def _capture_index_request(
        _workspace: Path,
        *,
        selected_repositories: list[Path] | None = None,
        **_kwargs: object,
    ) -> None:
        if not selected_repositories:
            return
        for repo_path in selected_repositories:
            resolved = Path(repo_path).resolve()
            if resolved not in selected:
                selected.append(resolved)

    run_repo_sync_cycle_fn(config, index_workspace=_capture_index_request)
    return sorted(selected, key=str)


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
        language = str(file_data.get("language") or "").strip() or None
        facts.append(
            file_fact(
                repo_path=repo_path,
                repo_id=repo_id,
                file_path=file_path,
                language=language,
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
                language=language,
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
