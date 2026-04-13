# src/platform_context_graph/core/watcher.py
"""Repo-partitioned live file watching for indexed workspaces."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from watchdog.observers import Observer

from platform_context_graph.utils.debug_log import info_logger, warning_logger
from .watch_repository import RepositoryEventHandler, RepositoryIndexer
from .watch_targets import WatchPlan, resolve_watch_targets, watch_debounce_seconds


class CodeWatcher:
    """Manage repo-partitioned filesystem watches for one process."""

    def __init__(
        self,
        index_repository: RepositoryIndexer,
    ) -> None:
        """Initialize one process-wide watcher manager and its root registries."""

        self.index_repository = index_repository
        self.observer = Observer()
        self.watched_paths: set[str] = set()
        self.watches: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, dict[str, RepositoryEventHandler]] = {}
        self._plans: dict[str, WatchPlan] = {}
        self._watch_configs: dict[str, dict[str, Any]] = {}
        self._refresh_stop_events: dict[str, threading.Event] = {}
        self._refresh_threads: dict[str, threading.Thread] = {}

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
            self.index_repository,
            repo_path,
            debounce_interval=watch_debounce_seconds(),
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
