"""Repository-local event handlers that trigger Go-owned repo reindexing."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler

from platform_context_graph.utils.debug_log import info_logger

RepositoryIndexer = Callable[[Path], None]


class RepositoryEventHandler(FileSystemEventHandler):
    """Debounce one repository's filesystem events into repo-level reindex runs."""

    def __init__(
        self,
        index_repository: Callable[[Path], None] | Callable[..., None],
        repo_path: Path,
        debounce_interval: float = 2.0,
        perform_initial_scan: bool = True,
    ) -> None:
        """Initialize one repo-local event handler.

        Args:
            index_repository: Callback that reindexes one repository path.
            repo_path: Repository root to monitor.
            debounce_interval: Batch debounce window in seconds.
            perform_initial_scan: Whether to trigger one non-forced reindex on
                startup before watching incremental changes.
        """

        super().__init__()
        self.index_repository = index_repository
        self.repo_path = repo_path.resolve()
        self.debounce_interval = debounce_interval
        self._timer: threading.Timer | None = None
        self._state_lock = threading.Lock()
        self._pending_paths: set[str] = set()

        if perform_initial_scan:
            self._run_index(force=False)

    def _run_index(self, *, force: bool) -> None:
        """Run one repo-level reindex via the injected callback."""

        info_logger(
            f"Starting watcher reindex for {self.repo_path} (force={str(force).lower()})"
        )
        self.index_repository(self.repo_path, force=force)
        info_logger(f"Watcher reindex complete for: {self.repo_path}")

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

        del deleted
        resolved = str(Path(event_path).resolve())
        with self._state_lock:
            self._pending_paths.add(resolved)
        self._schedule_batch()

    def _drain_pending(self) -> set[str]:
        """Detach the current batch of pending file changes."""

        with self._state_lock:
            pending_paths = set(self._pending_paths)
            self._pending_paths.clear()
            self._timer = None
        return pending_paths

    def _process_pending_changes(self) -> None:
        """Apply one coalesced batch of file changes through repo reindexing."""

        pending_paths = self._drain_pending()
        if not pending_paths:
            return

        info_logger(
            f"Refreshing watcher state for {self.repo_path} "
            f"({len(pending_paths)} changed files)"
        )
        self._run_index(force=True)

    def cleanup(self) -> None:
        """Cancel pending timers before the watcher is torn down."""

        with self._state_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending_paths.clear()

    def on_created(self, event) -> None:
        """Queue supported file creations for the next incremental batch."""

        if not event.is_directory and self._should_track_path(Path(event.src_path)):
            self._queue_event(event.src_path)

    def on_modified(self, event) -> None:
        """Queue supported file modifications for the next incremental batch."""

        if not event.is_directory and self._should_track_path(Path(event.src_path)):
            self._queue_event(event.src_path)

    def on_deleted(self, event) -> None:
        """Queue supported file deletions for the next incremental batch."""

        if not event.is_directory and self._should_track_path(Path(event.src_path)):
            self._queue_event(event.src_path, deleted=True)

    def on_moved(self, event) -> None:
        """Queue supported file move events as repo-level refreshes."""

        if event.is_directory:
            return
        if self._should_track_path(Path(event.src_path)):
            self._queue_event(event.src_path, deleted=True)
            return
        if self._should_track_path(Path(event.dest_path)):
            self._queue_event(event.dest_path)

    def _should_track_path(self, path: Path) -> bool:
        """Return whether a watcher event path should trigger a refresh batch."""

        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self.repo_path)
        except ValueError:
            return False
        if not relative.parts:
            return False
        return relative.parts[0] != ".git"


__all__ = ["RepositoryEventHandler", "RepositoryIndexer"]
