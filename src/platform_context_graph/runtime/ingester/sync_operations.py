"""Filesystem and Git sync operations for repo ingester runtimes."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from .config import RepoSyncConfig, RepoSyncResult
from .repository_layout import managed_repository_roots


def _run_sync_filesystem(
    config: RepoSyncConfig,
    *,
    index_workspace: Callable[..., None],
    fingerprint_tree_fn: Callable[..., str],
    manifest_path_fn: Callable[..., object],
    log_fn: Callable[..., None],
    filesystem_sync_all_fn: Callable[..., list[str]],
    begin_index_cycle_fn: Callable[..., object],
    record_phase_fn: Callable[..., None],
    repo_checkout_name_fn: Callable[[str], str],
    request_index_fn: Callable[..., None],
) -> RepoSyncResult:
    """Run a filesystem-backed repo sync cycle."""

    if config.filesystem_root is None:
        raise ValueError("filesystem source mode requires PCG_FILESYSTEM_ROOT")

    current_manifest = fingerprint_tree_fn(config.filesystem_root)
    fixture_manifest_path = manifest_path_fn(config)
    previous_manifest = (
        fixture_manifest_path.read_text(encoding="utf-8").strip()
        if fixture_manifest_path.exists()
        else ""
    )
    if current_manifest == previous_manifest:
        log_fn(config.component, "No fixture changes detected")
        return RepoSyncResult()

    discovered = filesystem_sync_all_fn(config)
    discovered_count = len(discovered)
    with begin_index_cycle_fn(config=config, mode="sync", repo_count=discovered_count):
        record_phase_fn(
            config=config,
            mode="sync",
            phase="discovered",
            count=discovered_count,
        )
        record_phase_fn(
            config=config,
            mode="sync",
            phase="updated",
            count=discovered_count,
        )
        record_phase_fn(
            config=config,
            mode="sync",
            phase="indexed",
            count=discovered_count,
        )
        selected_repositories = [
            (config.repos_dir / repo_checkout_name_fn(repo_id)).resolve()
            for repo_id in discovered
        ]
        request_index_fn(
            config,
            index_workspace,
            selected_repositories=selected_repositories,
            family="sync",
        )
        fixture_manifest_path.write_text(current_manifest, encoding="utf-8")
    return RepoSyncResult(
        discovered=discovered_count,
        updated=discovered_count,
        indexed=discovered_count,
    )


def _run_sync_git(
    config: RepoSyncConfig,
    *,
    index_workspace: Callable[..., None],
    git_token_fn: Callable[..., str],
    clone_missing_repositories_detailed_fn: Callable[..., tuple],
    update_existing_repositories_detailed_fn: Callable[..., tuple],
    count_stale_checkouts_fn: Callable[..., int],
    graph_missing_repository_paths_fn: Callable[..., list[Path]],
    repo_checkout_name_fn: Callable[[str], str],
    resumable_repository_paths_fn: Callable[[Path], Iterable[Path]],
    begin_index_cycle_fn: Callable[..., object],
    record_phase_fn: Callable[..., None],
    request_index_fn: Callable[..., None],
    log_fn: Callable[..., None],
) -> RepoSyncResult:
    """Run a Git-backed repo sync cycle."""

    def _repo_label(path: Path) -> str:
        """Return a workspace-relative repository label when possible."""

        resolved_path = path.resolve()
        try:
            return resolved_path.relative_to(config.repos_dir.resolve()).as_posix()
        except ValueError:
            return resolved_path.name

    token = git_token_fn(config)
    discovered, cloned_paths, clone_skipped, clone_failed = (
        clone_missing_repositories_detailed_fn(config, token)
    )
    updated_paths, update_failed = update_existing_repositories_detailed_fn(
        config, token
    )
    cloned = len(cloned_paths)
    updated = len(updated_paths)
    stale = count_stale_checkouts_fn(config, discovered)
    failed = clone_failed + update_failed
    discovered_repository_paths = [
        (config.repos_dir / repo_checkout_name_fn(repo_id)).resolve()
        for repo_id in discovered
    ]
    discovered_repository_path_set = set(discovered_repository_paths)
    resumable_repository_paths = {
        repo_path.resolve()
        for repo_path in resumable_repository_paths_fn(config.repos_dir)
    }
    resumable_managed_repositories = sorted(
        discovered_repository_path_set.intersection(resumable_repository_paths),
        key=str,
    )
    graph_missing_repositories = graph_missing_repository_paths_fn(
        discovered_repository_paths
    )
    selected_repositories = sorted(
        {
            *[repo_path.resolve() for repo_path in cloned_paths],
            *[repo_path.resolve() for repo_path in updated_paths],
            *graph_missing_repositories,
            *resumable_managed_repositories,
        },
        key=str,
    )
    should_index = bool(selected_repositories)
    if not should_index:
        with begin_index_cycle_fn(
            config=config, mode="sync", repo_count=len(discovered)
        ):
            record_phase_fn(
                config=config,
                mode="sync",
                phase="discovered",
                count=len(discovered),
            )
            if clone_skipped:
                record_phase_fn(
                    config=config,
                    mode="sync",
                    phase="skipped",
                    count=clone_skipped,
                )
            if failed:
                record_phase_fn(
                    config=config,
                    mode="sync",
                    phase="failed",
                    count=failed,
                )
            if stale:
                record_phase_fn(
                    config=config,
                    mode="sync",
                    phase="stale",
                    count=stale,
                )
            log_fn(
                config.component,
                "No repository changes detected; skipping re-index",
            )
            if stale:
                log_fn(
                    config.component,
                    f"Leaving {stale} stale checkout(s) unmanaged in the workspace",
                )
            return RepoSyncResult(
                discovered=len(discovered),
                skipped=clone_skipped,
                failed=failed,
                stale=stale,
            )

    discovered_count = len(managed_repository_roots(config.repos_dir))
    if graph_missing_repositories:
        preview = ", ".join(
            _repo_label(path) for path in graph_missing_repositories[:5]
        )
        if len(graph_missing_repositories) > 5:
            preview = f"{preview}, ..."
        log_fn(
            config.component,
            "Recovering repositories with missing or drifted graph state: "
            f"count={len(graph_missing_repositories)} repos={preview}",
        )
    with begin_index_cycle_fn(config=config, mode="sync", repo_count=discovered_count):
        record_phase_fn(
            config=config,
            mode="sync",
            phase="discovered",
            count=len(discovered),
        )
        if cloned:
            record_phase_fn(
                config=config,
                mode="sync",
                phase="cloned",
                count=cloned,
            )
        if updated:
            record_phase_fn(
                config=config,
                mode="sync",
                phase="updated",
                count=updated,
            )
        if clone_skipped:
            record_phase_fn(
                config=config,
                mode="sync",
                phase="skipped",
                count=clone_skipped,
            )
        if failed:
            record_phase_fn(
                config=config,
                mode="sync",
                phase="failed",
                count=failed,
            )
        if stale:
            record_phase_fn(
                config=config,
                mode="sync",
                phase="stale",
                count=stale,
            )
        record_phase_fn(
            config=config,
            mode="sync",
            phase="indexed",
            count=discovered_count,
        )
        request_index_fn(
            config,
            index_workspace,
            selected_repositories=selected_repositories,
            family="sync",
        )
    return RepoSyncResult(
        discovered=len(discovered),
        cloned=cloned,
        updated=updated,
        skipped=clone_skipped,
        failed=failed,
        stale=stale,
        indexed=len(selected_repositories),
    )
