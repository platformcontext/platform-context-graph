# src/platform_context_graph/core/watcher.py
"""Repo-partitioned live file watching for indexed workspaces."""

from __future__ import annotations

import fnmatch
import os
import threading
from dataclasses import dataclass
from pathlib import Path
import typing

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from platform_context_graph.utils.debug_log import info_logger, warning_logger

if typing.TYPE_CHECKING:
    from platform_context_graph.core.jobs import JobManager
    from platform_context_graph.tools.graph_builder import GraphBuilder


VALID_WATCH_SCOPES = {"auto", "repo", "workspace"}


def _watch_debounce_seconds() -> float:
    """Return the configured debounce interval for incremental watch batches."""

    raw_value = os.getenv("PCG_WATCH_DEBOUNCE_SECONDS", "2.0").strip()
    try:
        return max(0.1, min(float(raw_value), 60.0))
    except ValueError:
        return 2.0


@dataclass(slots=True)
class WatchPlan:
    """Resolved watch configuration for one requested path."""

    root_path: Path
    scope: str
    repository_paths: list[Path]


def _discover_repository_roots(path: Path) -> list[Path]:
    """Return nested git repository roots under ``path``."""

    if not path.is_dir():
        return []
    return sorted(
        {git_dir.parent.resolve() for git_dir in path.rglob(".git") if git_dir.is_dir()}
    )


def _matches_repository_patterns(repo_path: Path, patterns: list[str] | None) -> bool:
    """Return whether a repository matches any include/exclude pattern."""

    if not patterns:
        return False
    candidates = {repo_path.name, str(repo_path), repo_path.as_posix()}
    return any(
        fnmatch.fnmatch(candidate, pattern)
        for pattern in patterns
        for candidate in candidates
    )


def resolve_watch_targets(
    path: str | Path,
    *,
    scope: str = "auto",
    include_repositories: list[str] | None = None,
    exclude_repositories: list[str] | None = None,
) -> WatchPlan:
    """Resolve a watch request into repo-partitioned targets."""

    normalized_scope = scope.lower().strip()
    if normalized_scope not in VALID_WATCH_SCOPES:
        raise ValueError(
            f"Unsupported watch scope '{scope}'. Expected one of: "
            f"{', '.join(sorted(VALID_WATCH_SCOPES))}"
        )

    root_path = Path(path).resolve()
    if not root_path.exists():
        raise FileNotFoundError(root_path)
    if not root_path.is_dir():
        raise NotADirectoryError(root_path)

    direct_repo = (root_path / ".git").exists()
    discovered_repos = _discover_repository_roots(root_path)
    if direct_repo and root_path not in discovered_repos:
        discovered_repos.insert(0, root_path)

    effective_scope = normalized_scope
    if normalized_scope == "repo":
        repository_paths = [root_path]
    elif normalized_scope == "workspace":
        effective_scope = "workspace"
        repository_paths = discovered_repos or [root_path]
    elif direct_repo or not discovered_repos:
        effective_scope = "repo"
        repository_paths = [root_path]
    else:
        effective_scope = "workspace"
        repository_paths = discovered_repos

    filtered_repositories = []
    for repo_path in repository_paths:
        if include_repositories and not _matches_repository_patterns(
            repo_path,
            include_repositories,
        ):
            continue
        if _matches_repository_patterns(repo_path, exclude_repositories):
            continue
        filtered_repositories.append(repo_path.resolve())

    if not filtered_repositories:
        raise ValueError(
            "Watch filters excluded every repository under the target path"
        )

    return WatchPlan(
        root_path=root_path,
        scope=effective_scope,
        repository_paths=sorted(filtered_repositories),
    )


class RepositoryEventHandler(FileSystemEventHandler):
    """Incremental watcher state for one repository."""

    def __init__(
        self,
        graph_builder: "GraphBuilder",
        repo_path: Path,
        debounce_interval: float = 2.0,
        perform_initial_scan: bool = True,
    ) -> None:
        super().__init__()
        self.graph_builder = graph_builder
        self.repo_path = repo_path.resolve()
        self.debounce_interval = debounce_interval
        self._timer: threading.Timer | None = None
        self._state_lock = threading.Lock()
        self._pending_paths: set[str] = set()
        self._pending_deleted_paths: set[str] = set()
        self.file_data_by_path: dict[str, dict[str, typing.Any]] = {}
        self.imports_map: dict[str, list[str]] = {}

        if perform_initial_scan:
            self._initial_scan()

    def _supported_files(self) -> list[Path]:
        """Return all parser-supported files in the repository."""

        supported_extensions = set(self.graph_builder.parsers.keys())
        return sorted(
            file_path
            for file_path in self.repo_path.rglob("*")
            if file_path.is_file() and file_path.suffix in supported_extensions
        )

    def _relink_repository(self) -> None:
        """Recreate cross-file relationships from the current repo cache."""

        file_data = list(self.file_data_by_path.values())
        self.graph_builder._create_all_function_calls(file_data, self.imports_map)
        self.graph_builder._create_all_inheritance_links(file_data, self.imports_map)
        self.graph_builder._create_all_infra_links(file_data)

    def _initial_scan(self) -> None:
        """Populate the in-memory cache for one repository."""

        info_logger(f"Performing initial watcher scan for: {self.repo_path}")
        files = self._supported_files()
        self.imports_map = self.graph_builder._pre_scan_for_imports(files)
        self.file_data_by_path = {}
        for file_path in files:
            parsed_data = self.graph_builder.parse_file(self.repo_path, file_path)
            if "error" in parsed_data:
                continue
            self.file_data_by_path[str(file_path.resolve())] = parsed_data
        self._relink_repository()
        info_logger(f"Initial watcher scan complete for: {self.repo_path}")

    def _schedule_batch(self) -> None:
        """Restart the debounce timer for the next incremental update batch."""

        with self._state_lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                self.debounce_interval,
                self._process_pending_changes,
            )
            self._timer.start()

    def _queue_event(self, event_path: str, *, deleted: bool = False) -> None:
        """Add a path to the pending batch and reset the debounce timer."""

        resolved = str(Path(event_path).resolve())
        with self._state_lock:
            self._pending_paths.add(resolved)
            if deleted:
                self._pending_deleted_paths.add(resolved)
        self._schedule_batch()

    def _drain_pending(self) -> tuple[set[str], set[str]]:
        """Detach the current batch of pending file changes."""

        with self._state_lock:
            pending_paths = set(self._pending_paths)
            deleted_paths = set(self._pending_deleted_paths)
            self._pending_paths.clear()
            self._pending_deleted_paths.clear()
            self._timer = None
        return pending_paths, deleted_paths

    def _process_pending_changes(self) -> None:
        """Apply one coalesced batch of file changes to the graph."""

        pending_paths, deleted_paths = self._drain_pending()
        if not pending_paths and not deleted_paths:
            return

        info_logger(
            f"Refreshing watcher state for {self.repo_path} "
            f"({len(pending_paths | deleted_paths)} changed files)"
        )
        files = self._supported_files()
        self.imports_map = self.graph_builder._pre_scan_for_imports(files)
        current_files = {str(file_path.resolve()) for file_path in files}

        for deleted_path in sorted(deleted_paths):
            self.graph_builder.delete_file_from_graph(deleted_path)
            self.file_data_by_path.pop(deleted_path, None)

        for pending_path in sorted(pending_paths):
            if pending_path not in current_files:
                self.file_data_by_path.pop(pending_path, None)
                continue
            updated = self.graph_builder.update_file_in_graph(
                Path(pending_path),
                self.repo_path,
                self.imports_map,
            )
            if updated is None or updated.get("deleted"):
                self.file_data_by_path.pop(pending_path, None)
                continue
            self.file_data_by_path[pending_path] = updated

        stale_paths = [
            file_path
            for file_path in self.file_data_by_path
            if file_path not in current_files
        ]
        for stale_path in stale_paths:
            self.file_data_by_path.pop(stale_path, None)

        self._relink_repository()
        info_logger(f"Watcher refresh complete for: {self.repo_path}")

    def cleanup(self) -> None:
        """Cancel pending timers before the watcher is torn down."""

        with self._state_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending_paths.clear()
            self._pending_deleted_paths.clear()

    def on_created(self, event) -> None:
        if (
            not event.is_directory
            and Path(event.src_path).suffix in self.graph_builder.parsers
        ):
            self._queue_event(event.src_path)

    def on_modified(self, event) -> None:
        if (
            not event.is_directory
            and Path(event.src_path).suffix in self.graph_builder.parsers
        ):
            self._queue_event(event.src_path)

    def on_deleted(self, event) -> None:
        if (
            not event.is_directory
            and Path(event.src_path).suffix in self.graph_builder.parsers
        ):
            self._queue_event(event.src_path, deleted=True)

    def on_moved(self, event) -> None:
        if event.is_directory:
            return
        if Path(event.src_path).suffix in self.graph_builder.parsers:
            self._queue_event(event.src_path, deleted=True)
        if Path(event.dest_path).suffix in self.graph_builder.parsers:
            self._queue_event(event.dest_path)


class CodeWatcher:
    """Manage repo-partitioned filesystem watches for one process."""

    def __init__(
        self,
        graph_builder: "GraphBuilder",
        job_manager: "JobManager | None" = None,
    ) -> None:
        self.graph_builder = graph_builder
        self.observer = Observer()
        self.watched_paths: set[str] = set()
        self.watches: dict[str, dict[str, typing.Any]] = {}
        self._handlers: dict[str, dict[str, RepositoryEventHandler]] = {}
        self._plans: dict[str, WatchPlan] = {}
        self._watch_configs: dict[str, dict[str, typing.Any]] = {}
        self._refresh_stop_events: dict[str, threading.Event] = {}
        self._refresh_threads: dict[str, threading.Thread] = {}
        self.job_manager = job_manager

    def _add_repository_watch(
        self,
        path_str: str,
        repo_path: Path,
        *,
        perform_initial_scan: bool,
    ) -> None:
        """Attach one repo-specific handler under an existing watched root."""

        repo_key = str(repo_path.resolve())
        if repo_key in self._handlers[path_str]:
            return

        handler = RepositoryEventHandler(
            self.graph_builder,
            repo_path,
            debounce_interval=_watch_debounce_seconds(),
            perform_initial_scan=perform_initial_scan,
        )
        watch = self.observer.schedule(handler, str(repo_path), recursive=True)
        self._handlers[path_str][repo_key] = handler
        self.watches[path_str][repo_key] = watch

    def _remove_repository_watch(self, path_str: str, repo_path: Path) -> None:
        """Detach one repo-specific handler from an existing watched root."""

        repo_key = str(repo_path.resolve())
        handler = self._handlers.get(path_str, {}).pop(repo_key, None)
        if handler is not None:
            handler.cleanup()
        watch = self.watches.get(path_str, {}).pop(repo_key, None)
        if watch is not None:
            self.observer.unschedule(watch)

    def _stop_refresh_thread(self, path_str: str) -> None:
        """Stop the background rediscovery thread for one watched root."""

        stop_event = self._refresh_stop_events.pop(path_str, None)
        if stop_event is not None:
            stop_event.set()
        thread = self._refresh_threads.pop(path_str, None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def _refresh_loop(
        self,
        path_str: str,
        interval_seconds: float,
        stop_event: threading.Event,
    ) -> None:
        """Run periodic repo rediscovery for one workspace watch."""

        while not stop_event.wait(interval_seconds):
            if path_str not in self.watched_paths:
                return
            try:
                self.refresh_watch_directory(path_str)
            except Exception as exc:
                warning_logger(
                    f"Workspace watch rediscovery failed for {path_str}: {exc}"
                )

    def _start_refresh_thread(self, path_str: str, interval_seconds: float) -> None:
        """Start periodic repo rediscovery for a watched workspace."""

        if interval_seconds <= 0:
            return
        self._stop_refresh_thread(path_str)
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._refresh_loop,
            args=(path_str, interval_seconds, stop_event),
            daemon=True,
        )
        self._refresh_stop_events[path_str] = stop_event
        self._refresh_threads[path_str] = thread
        thread.start()

    def watch_directory(
        self,
        path: str,
        perform_initial_scan: bool = True,
        *,
        scope: str = "auto",
        include_repositories: list[str] | None = None,
        exclude_repositories: list[str] | None = None,
        rediscover_interval_seconds: int | None = None,
    ) -> dict[str, typing.Any]:
        """Schedule a path for watching using repo-partitioned handlers."""

        path_obj = Path(path).resolve()
        path_str = str(path_obj)

        if path_str in self.watched_paths:
            info_logger(f"Path already being watched: {path_str}")
            return {"message": f"Path already being watched: {path_str}"}

        plan = resolve_watch_targets(
            path_obj,
            scope=scope,
            include_repositories=include_repositories,
            exclude_repositories=exclude_repositories,
        )

        self.watches[path_str] = {}
        self._handlers[path_str] = {}
        self._plans[path_str] = plan
        self._watch_configs[path_str] = {
            "scope": scope,
            "include_repositories": include_repositories,
            "exclude_repositories": exclude_repositories,
            "rediscover_interval_seconds": rediscover_interval_seconds,
        }
        for repo_path in plan.repository_paths:
            self._add_repository_watch(
                path_str,
                repo_path,
                perform_initial_scan=perform_initial_scan,
            )

        if (
            rediscover_interval_seconds is not None
            and plan.scope == "workspace"
            and rediscover_interval_seconds > 0
        ):
            self._start_refresh_thread(path_str, float(rediscover_interval_seconds))

        self.watched_paths.add(path_str)
        info_logger(
            f"Started watching {path_str} as {plan.scope} "
            f"({len(plan.repository_paths)} repos)"
        )
        return {
            "message": f"Started watching {path_str}.",
            "scope": plan.scope,
            "repository_count": len(plan.repository_paths),
            "repositories": [str(repo_path) for repo_path in plan.repository_paths],
        }

    def refresh_watch_directory(self, path: str) -> dict[str, typing.Any]:
        """Refresh a watched workspace and attach/detach repo handlers as needed."""

        path_obj = Path(path).resolve()
        path_str = str(path_obj)
        if path_str not in self.watched_paths:
            return {"error": f"Path not currently being watched: {path_str}"}

        config = self._watch_configs.get(path_str, {})
        updated_plan = resolve_watch_targets(
            path_obj,
            scope=str(config.get("scope", "auto")),
            include_repositories=config.get("include_repositories"),
            exclude_repositories=config.get("exclude_repositories"),
        )
        current_repositories = set(self._plans[path_str].repository_paths)
        updated_repositories = set(updated_plan.repository_paths)
        removed_repositories = sorted(current_repositories - updated_repositories)
        added_repositories = sorted(updated_repositories - current_repositories)

        for repo_path in removed_repositories:
            self._remove_repository_watch(path_str, repo_path)
        for repo_path in added_repositories:
            self._add_repository_watch(
                path_str,
                repo_path,
                perform_initial_scan=True,
            )

        self._plans[path_str] = updated_plan
        if added_repositories or removed_repositories:
            info_logger(
                f"Refreshed watch plan for {path_str}: "
                f"+{len(added_repositories)} / -{len(removed_repositories)} repos"
            )
        return {
            "message": f"Refreshed watched workspace {path_str}.",
            "scope": updated_plan.scope,
            "repository_count": len(updated_plan.repository_paths),
            "added_repositories": [str(repo_path) for repo_path in added_repositories],
            "removed_repositories": [
                str(repo_path) for repo_path in removed_repositories
            ],
        }

    def unwatch_directory(self, path: str) -> dict[str, str]:
        """Stop watching a previously watched root path."""

        path_obj = Path(path).resolve()
        path_str = str(path_obj)

        if path_str not in self.watched_paths:
            warning_logger(
                f"Attempted to unwatch a path that is not being watched: {path_str}"
            )
            return {"error": f"Path not currently being watched: {path_str}"}

        self._stop_refresh_thread(path_str)
        for repo_key in list(self._handlers.get(path_str, {})):
            self._remove_repository_watch(path_str, Path(repo_key))

        self._handlers.pop(path_str, None)
        self.watches.pop(path_str, None)
        self._plans.pop(path_str, None)
        self._watch_configs.pop(path_str, None)
        self.watched_paths.discard(path_str)
        info_logger(f"Stopped watching for code changes in: {path_str}")
        return {"message": f"Stopped watching {path_str}."}

    def list_watched_paths(self) -> list[str]:
        """Return the currently watched root paths."""

        return sorted(self.watched_paths)

    def start(self) -> None:
        """Start the underlying watchdog observer thread."""

        if not self.observer.is_alive():
            self.observer.start()
            info_logger("Code watcher observer thread started.")

    def stop(self) -> None:
        """Stop the observer and clean up handler timers."""

        for path_str in list(self._refresh_stop_events):
            self._stop_refresh_thread(path_str)

        for handlers in self._handlers.values():
            for handler in handlers.values():
                handler.cleanup()

        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            info_logger("Code watcher observer thread stopped.")

        self.watched_paths.clear()
        self.watches.clear()
        self._handlers.clear()
        self._plans.clear()
        self._watch_configs.clear()
