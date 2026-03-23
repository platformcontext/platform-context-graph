"""Repository-local event handlers for incremental watch updates."""

from __future__ import annotations

import threading
from pathlib import Path
import typing

from watchdog.events import FileSystemEventHandler

from platform_context_graph.utils.debug_log import info_logger

if typing.TYPE_CHECKING:
    from platform_context_graph.tools.graph_builder import GraphBuilder


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


__all__ = ["RepositoryEventHandler"]
