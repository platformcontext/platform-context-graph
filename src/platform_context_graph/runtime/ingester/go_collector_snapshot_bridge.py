"""Narrowed snapshot bridge for the Go ``collector-git`` runtime."""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

from .config import RepoSyncConfig
from .go_collector_snapshot_collection import collect_repository_snapshot


def collect_snapshot_batch(
    config: RepoSyncConfig,
    *,
    repo_path: Path,
    resolve_repository_file_sets_fn: Callable[..., dict[Path, list[Path]]] | None = None,
    parse_repository_snapshot_async_fn: Callable[..., Any] | None = None,
    build_parser_registry_fn: Callable[..., dict[str, Any]] | None = None,
    git_remote_for_path_fn: Callable[[Path], str | None] | None = None,
    utc_now_fn,
    pathspec_module: object | None = None,
) -> dict[str, Any]:
    """Collect one narrowed repository snapshot in the JSON contract expected by Go."""

    return collect_repository_snapshot(
        config,
        repo_path=repo_path,
        resolve_repository_file_sets_fn=resolve_repository_file_sets_fn,
        parse_repository_snapshot_async_fn=parse_repository_snapshot_async_fn,
        build_parser_registry_fn=build_parser_registry_fn,
        git_remote_for_path_fn=git_remote_for_path_fn,
        utc_now_fn=utc_now_fn,
        pathspec_module=pathspec_module,
    )


def main() -> int:
    """Run one repo-sync cycle and print one repository snapshot as JSON."""

    from platform_context_graph.facts.models.base import utc_now

    config = RepoSyncConfig.from_env(component="collector-git-snapshot-bridge")
    with contextlib.redirect_stdout(sys.stderr):
        batch = collect_repository_snapshot(
            config,
            repo_path=config.repos_dir,
            utc_now_fn=utc_now,
        )
    json.dump(batch, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
