"""MCP handler functions for file-watcher operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ....utils.debug_log import error_logger


def list_watched_paths(code_watcher, **args: Any) -> dict[str, Any]:
    """Tool to list all currently watched directory paths."""
    try:
        paths = code_watcher.list_watched_paths()
        return {"success": True, "watched_paths": paths}
    except Exception as exc:
        return {"error": f"Failed to list watched paths: {str(exc)}"}


def unwatch_directory(code_watcher, **args: Any) -> dict[str, Any]:
    """Tool to stop watching a directory."""
    path = args.get("path")
    if not path:
        return {"error": "Path is a required argument."}
    return code_watcher.unwatch_directory(path)


# watch_directory is complex as it depends on other tools and handlers
# We will keep it in server.py or implement it here passing all dependencies.
# Let's implement it here as a pure function accepting dependencies.
# Dependencies: code_watcher, list_repositories_func, add_code_func


def watch_directory(
    code_watcher, list_repositories_func, add_code_func, **args: Any
) -> dict[str, Any]:
    """
    Tool implementation to start watching a directory for changes.
    It checks if the path exists, if it's already watched, or if it needs indexing.
    """
    path = args.get("path")
    if not path:
        return {"error": "Path is a required argument."}

    path_obj = Path(path).resolve()
    path_str = str(path_obj)

    # 1. Validate the path
    if not path_obj.is_dir():
        return {
            "success": True,
            "status": "path_not_found",
            "message": f"Path '{path_str}' does not exist or is not a directory.",
        }
    try:
        # Check if already watching
        if path_str in code_watcher.watched_paths:
            return {
                "success": True,
                "message": f"Already watching directory: {path_str}",
            }

        # 2. Check if the repository is already indexed
        indexed_repos_result = list_repositories_func()
        indexed_repos = indexed_repos_result.get("repositories", [])
        is_already_indexed = any(
            repo.get("local_path") and Path(repo["local_path"]).resolve() == path_obj
            for repo in indexed_repos
        )

        # 3. Decide whether to perform an initial scan
        if is_already_indexed:
            # If already indexed, just start the watcher without a scan
            code_watcher.watch_directory(
                path_str,
                perform_initial_scan=False,
                scope=args.get("scope", "auto"),
                include_repositories=args.get("include_repositories"),
                exclude_repositories=args.get("exclude_repositories"),
            )
            return {
                "success": True,
                "message": f"Path '{path_str}' is already indexed. Now watching for live changes.",
            }
        else:
            # If not indexed, perform the scan AND start the watcher
            scan_job_result = add_code_func(path=path_str, is_dependency=False)

            if "error" in scan_job_result:
                return scan_job_result

            code_watcher.watch_directory(
                path_str,
                perform_initial_scan=False,
                scope=args.get("scope", "auto"),
                include_repositories=args.get("include_repositories"),
                exclude_repositories=args.get("exclude_repositories"),
            )

            return {
                "success": True,
                "message": f"Path '{path_str}' was not indexed. Started initial scan and now watching for live changes.",
                "job_id": scan_job_result.get("job_id"),
                "details": "Use check_job_status to monitor the initial scan.",
            }

    except Exception as exc:
        error_logger(f"Failed to start watching directory {path}: {exc}")
        return {"error": f"Failed to start watching directory: {str(exc)}"}
