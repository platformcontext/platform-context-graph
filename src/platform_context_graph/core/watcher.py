# src/platform_context_graph/core/watcher.py
"""
This module implements the live file-watching functionality using the `watchdog` library.
It observes directories for changes and triggers updates to the code graph.
"""

import threading
from pathlib import Path
import typing
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

if typing.TYPE_CHECKING:
    from platform_context_graph.tools.graph_builder import GraphBuilder
    from platform_context_graph.core.jobs import JobManager

from platform_context_graph.utils.debug_log import (
    debug_log,
    info_logger,
    error_logger,
    warning_logger,
)


class RepositoryEventHandler(FileSystemEventHandler):
    """
    A dedicated event handler for a single repository being watched.

    This handler is stateful. It performs an initial scan of the repository
    to build a baseline and then uses this cached state to perform efficient
    updates when files are changed, created, or deleted.
    """

    def __init__(
        self,
        graph_builder: "GraphBuilder",
        repo_path: Path,
        debounce_interval=2.0,
        perform_initial_scan: bool = True,
    ):
        """
        Initializes the event handler.

        Args:
            graph_builder: An instance of the GraphBuilder to perform graph operations.
            repo_path: The absolute path to the repository directory to watch.
            debounce_interval: The time in seconds to wait for more changes before processing an event.
            perform_initial_scan: Whether to perform an initial scan of the repository.
        """
        super().__init__()
        self.graph_builder = graph_builder
        self.repo_path = repo_path
        self.debounce_interval = debounce_interval
        self.timers = {}  # A dictionary to manage debounce timers for file paths.

        # Caches for the repository's state.
        self.all_file_data = []
        self.imports_map = {}

        # Perform the initial scan and linking when the watcher is created.
        if perform_initial_scan:
            self._initial_scan()

    def _initial_scan(self):
        """Scans the entire repository, parses all files, and builds the initial graph."""
        info_logger(f"Performing initial scan for watcher: {self.repo_path}")
        supported_extensions = self.graph_builder.parsers.keys()
        all_files = [
            f
            for f in self.repo_path.rglob("*")
            if f.is_file() and f.suffix in supported_extensions
        ]

        # 1. Pre-scan all files to get a global map of where every symbol is defined.
        self.imports_map = self.graph_builder._pre_scan_for_imports(all_files)

        # 2. Parse all files in detail and cache the parsed data.
        for f in all_files:
            parsed_data = self.graph_builder.parse_file(self.repo_path, f)
            if "error" not in parsed_data:
                self.all_file_data.append(parsed_data)

        # 3. After all files are parsed, create the relationships (e.g., function calls) between them.
        self.graph_builder._create_all_function_calls(
            self.all_file_data, self.imports_map
        )
        self.graph_builder._create_all_inheritance_links(
            self.all_file_data, self.imports_map
        )
        info_logger(f"Initial scan and graph linking complete for: {self.repo_path}")

    def _debounce(self, event_path, action):
        """
        Schedules an action to run after a debounce interval.
        This prevents the handler from firing on every single file save event in rapid
        succession, which is common in IDEs. It waits for a quiet period before processing.
        """
        # If a timer already exists for this path, cancel it.
        if event_path in self.timers:
            self.timers[event_path].cancel()
        # Create and start a new timer.
        timer = threading.Timer(self.debounce_interval, action)
        timer.start()
        self.timers[event_path] = timer

    def _handle_modification(self, event_path_str: str):
        """
        Orchestrates the complete update cycle for a modified or created file.
        This involves re-scanning the entire repo to update cross-file relationships.
        """
        info_logger(
            f"File change detected, starting full repository refresh for: {event_path_str}"
        )
        modified_path = Path(event_path_str)

        # 1. Get all supported files in the repository.
        supported_extensions = self.graph_builder.parsers.keys()
        all_files = [
            f
            for f in self.repo_path.rglob("*")
            if f.is_file() and f.suffix in supported_extensions
        ]

        # 2. Re-scan all files to get a fresh, global map of all symbols.
        self.imports_map = self.graph_builder._pre_scan_for_imports(all_files)
        info_logger("Refreshed global imports map.")

        # 3. Update the specific file that changed in the graph.
        # This deletes old nodes and adds new ones for the single file.
        self.graph_builder.update_file_in_graph(
            modified_path, self.repo_path, self.imports_map
        )

        # 4. Re-parse all files to have a complete, in-memory representation for the linking pass.
        # This is necessary because a change in one file can affect relationships in others.
        self.all_file_data = []
        for f in all_files:
            parsed_data = self.graph_builder.parse_file(self.repo_path, f)
            if "error" not in parsed_data:
                self.all_file_data.append(parsed_data)
        info_logger("Refreshed in-memory cache of all file data.")

        # 5. CRITICAL: Re-link the entire graph using the fully updated cache and imports map.
        info_logger("Re-linking the entire graph for calls and inheritance...")
        self.graph_builder._create_all_function_calls(
            self.all_file_data, self.imports_map
        )
        self.graph_builder._create_all_inheritance_links(
            self.all_file_data, self.imports_map
        )
        info_logger(f"Graph refresh for change in {event_path_str} complete! ✅")

    # The following methods are called by the watchdog observer when a file event occurs.
    def on_created(self, event):
        """Handle created file events."""
        if (
            not event.is_directory
            and Path(event.src_path).suffix in self.graph_builder.parsers
        ):
            self._debounce(
                event.src_path, lambda: self._handle_modification(event.src_path)
            )

    def on_modified(self, event):
        """Handle modified file events."""
        if (
            not event.is_directory
            and Path(event.src_path).suffix in self.graph_builder.parsers
        ):
            self._debounce(
                event.src_path, lambda: self._handle_modification(event.src_path)
            )

    def on_deleted(self, event):
        """Handle deleted file events."""
        if (
            not event.is_directory
            and Path(event.src_path).suffix in self.graph_builder.parsers
        ):
            self._debounce(
                event.src_path, lambda: self._handle_modification(event.src_path)
            )

    def on_moved(self, event):
        """Handle moved file events."""
        if not event.is_directory:
            if Path(event.src_path).suffix in self.graph_builder.parsers:
                self._debounce(
                    event.src_path, lambda: self._handle_modification(event.src_path)
                )
            if Path(event.dest_path).suffix in self.graph_builder.parsers:
                self._debounce(
                    event.dest_path, lambda: self._handle_modification(event.dest_path)
                )


class CodeWatcher:
    """
    Manages the file system observer thread. It can watch multiple directories,
    assigning a separate `RepositoryEventHandler` to each one.
    """

    def __init__(
        self,
        graph_builder: "GraphBuilder",
        job_manager: "JobManager | None" = None,
    ):
        """Initialize the repository watcher coordinator."""
        self.graph_builder = graph_builder
        self.observer = Observer()
        self.watched_paths = set()  # Keep track of paths already being watched.
        self.watches = {}  # Store watch objects to allow unscheduling
        self.job_manager = job_manager

    def watch_directory(self, path: str, perform_initial_scan: bool = True):
        """Schedules a directory to be watched for changes."""
        path_obj = Path(path).resolve()
        path_str = str(path_obj)

        if path_str in self.watched_paths:
            info_logger(f"Path already being watched: {path_str}")
            return {"message": f"Path already being watched: {path_str}"}

        # Create a new, dedicated event handler for this specific repository path.
        event_handler = RepositoryEventHandler(
            self.graph_builder, path_obj, perform_initial_scan=perform_initial_scan
        )

        watch = self.observer.schedule(event_handler, path_str, recursive=True)
        self.watches[path_str] = watch
        self.watched_paths.add(path_str)
        info_logger(f"Started watching for code changes in: {path_str}")

        return {"message": f"Started watching {path_str}."}

    def unwatch_directory(self, path: str):
        """Stops watching a directory for changes."""
        path_obj = Path(path).resolve()
        path_str = str(path_obj)

        if path_str not in self.watched_paths:
            warning_logger(
                f"Attempted to unwatch a path that is not being watched: {path_str}"
            )
            return {"error": f"Path not currently being watched: {path_str}"}

        watch = self.watches.pop(path_str, None)
        if watch:
            self.observer.unschedule(watch)

        self.watched_paths.discard(path_str)
        info_logger(f"Stopped watching for code changes in: {path_str}")
        return {"message": f"Stopped watching {path_str}."}

    def list_watched_paths(self) -> list:
        """Returns a list of all currently watched directory paths."""
        return list(self.watched_paths)

    def start(self):
        """Starts the observer thread."""
        if not self.observer.is_alive():
            self.observer.start()
            info_logger("Code watcher observer thread started.")

    def stop(self):
        """Stops the observer thread gracefully."""
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()  # Wait for the thread to terminate.
            info_logger("Code watcher observer thread stopped.")
