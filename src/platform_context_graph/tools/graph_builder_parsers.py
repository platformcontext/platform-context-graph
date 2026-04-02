"""Compatibility shim for the canonical parser registry package."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..parsers import registry as _canonical

logger = logging.getLogger(__name__)

Parser = _canonical.Parser
get_tree_sitter_manager = _canonical.get_tree_sitter_manager
_load_attribute = _canonical._load_attribute
_LANGUAGE_SPECIFIC_PARSERS = _canonical._LANGUAGE_SPECIFIC_PARSERS
_EXTENSION_SPECIFIC_PARSERS = _canonical._EXTENSION_SPECIFIC_PARSERS
_TREE_SITTER_PARSER_EXTENSIONS = _canonical._TREE_SITTER_PARSER_EXTENSIONS
_PRE_SCAN_HANDLER_GROUPS = _canonical._PRE_SCAN_HANDLER_GROUPS


def _sync_canonical_globals() -> None:
    """Mirror legacy monkeypatch targets into the canonical parser module."""
    _canonical.logger = logger
    _canonical.Parser = Parser
    _canonical.get_tree_sitter_manager = get_tree_sitter_manager
    _canonical._load_attribute = _load_attribute
    _canonical._LANGUAGE_SPECIFIC_PARSERS = _LANGUAGE_SPECIFIC_PARSERS
    _canonical._EXTENSION_SPECIFIC_PARSERS = _EXTENSION_SPECIFIC_PARSERS
    _canonical._TREE_SITTER_PARSER_EXTENSIONS = _TREE_SITTER_PARSER_EXTENSIONS
    _canonical._PRE_SCAN_HANDLER_GROUPS = _PRE_SCAN_HANDLER_GROUPS
    _canonical.TreeSitterParser = TreeSitterParser


class TreeSitterParser(_canonical.TreeSitterParser):
    """Legacy parser wrapper that keeps old monkeypatch seams working."""

    def __init__(self, language_name: str):
        _sync_canonical_globals()
        super().__init__(language_name)


def build_parser_registry(get_config_value_fn: Any) -> dict[str, Any]:
    """Build the parser registry from the canonical parser package."""
    _sync_canonical_globals()
    return _canonical.build_parser_registry(get_config_value_fn)


def pre_scan_for_imports(builder: Any, files: list[Path]) -> dict[str, Any]:
    """Run import prescans through the canonical parser package."""
    _sync_canonical_globals()
    return _canonical.pre_scan_for_imports(builder, files)


def parse_file(
    builder: Any,
    repo_path: Path,
    path: Path,
    is_dependency: bool,
    *,
    get_config_value_fn: Any,
    debug_log_fn: Any,
    error_logger_fn: Any,
    warning_logger_fn: Any,
) -> dict[str, Any]:
    """Parse one file through the canonical parser package."""
    _sync_canonical_globals()
    return _canonical.parse_file(
        builder,
        repo_path,
        path,
        is_dependency,
        get_config_value_fn=get_config_value_fn,
        debug_log_fn=debug_log_fn,
        error_logger_fn=error_logger_fn,
        warning_logger_fn=warning_logger_fn,
    )


def parse_file_for_indexing_worker(
    repo_path: Path,
    path: Path,
    is_dependency: bool,
    *,
    get_config_value_fn: Any,
    debug_log_fn: Any,
    error_logger_fn: Any,
    warning_logger_fn: Any,
) -> dict[str, Any]:
    """Parse one file in a worker-friendly context with legacy compatibility."""
    _sync_canonical_globals()
    return _canonical.parse_file_for_indexing_worker(
        repo_path,
        path,
        is_dependency,
        get_config_value_fn=get_config_value_fn,
        debug_log_fn=debug_log_fn,
        error_logger_fn=error_logger_fn,
        warning_logger_fn=warning_logger_fn,
    )


__all__ = [
    "TreeSitterParser",
    "build_parser_registry",
    "parse_file_for_indexing_worker",
    "parse_file",
    "pre_scan_for_imports",
]
