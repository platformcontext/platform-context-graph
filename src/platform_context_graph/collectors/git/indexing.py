"""Git collector indexing and discovery helpers."""

from __future__ import annotations

from .discovery import (
    apply_ignore_spec,
    collect_supported_files,
    discover_git_repositories,
    discover_index_files,
    estimate_processing_time,
    find_pcgignore,
    get_ignored_dir_names,
    merge_import_maps,
    resolve_repository_file_sets,
)
from .types import RepositoryParseSnapshot

__all__ = [
    "RepositoryParseSnapshot",
    "apply_ignore_spec",
    "collect_supported_files",
    "discover_git_repositories",
    "discover_index_files",
    "estimate_processing_time",
    "find_pcgignore",
    "get_ignored_dir_names",
    "merge_import_maps",
    "resolve_repository_file_sets",
]
