"""Compatibility bridge for Go collector repository selection."""

from __future__ import annotations

import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .config import RepoSyncConfig


def _default_run_repo_sync_cycle(*args: object, **kwargs: object) -> Any:
    """Load repo-sync execution lazily."""

    from .sync import run_repo_sync_cycle

    return run_repo_sync_cycle(*args, **kwargs)


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


def collect_selection_batch(
    config: RepoSyncConfig,
    *,
    run_repo_sync_cycle_fn: Callable[..., object] | None = None,
    git_remote_for_path_fn: Callable[[Path], str | None],
    utc_now_fn: Callable[[], datetime],
) -> dict[str, Any]:
    """Collect one repo-selection cycle in the JSON contract expected by Go."""

    run_repo_sync_cycle_fn = run_repo_sync_cycle_fn or _default_run_repo_sync_cycle

    selected_repositories = _selected_repositories_for_cycle(
        config,
        run_repo_sync_cycle_fn=run_repo_sync_cycle_fn,
    )
    observed_at = utc_now_fn()
    return {
        "observed_at": observed_at.isoformat(),
        "repositories": [
            {
                "repo_path": str(repo_path.resolve()),
                "remote_url": git_remote_for_path_fn(repo_path),
            }
            for repo_path in selected_repositories
        ],
    }


def main() -> int:
    """Run one repo-sync cycle and print the selection batch as JSON."""

    from platform_context_graph.facts.models.base import utc_now
    from .go_collector_snapshot_collection import _default_git_remote_for_path

    config = RepoSyncConfig.from_env(component="collector-git-selection-bridge")
    with contextlib.redirect_stdout(sys.stderr):
        batch = collect_selection_batch(
            config,
            git_remote_for_path_fn=_default_git_remote_for_path,
            utc_now_fn=utc_now,
        )
    json.dump(batch, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
