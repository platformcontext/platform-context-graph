"""Process-pool worker helpers for repository file parsing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..cli.config_manager import get_config_value
from ..observability import initialize_observability
from ..utils.debug_log import error_logger, warning_logger
from .graph_builder_parsers import build_parser_registry, parse_file

_WORKER_BUILDER: SimpleNamespace | None = None


def init_parse_worker() -> None:
    """Initialize the process-local parser registry once per worker."""

    global _WORKER_BUILDER
    initialize_observability(component="repository")
    _WORKER_BUILDER = SimpleNamespace(parsers=build_parser_registry(get_config_value))


def _worker_builder() -> SimpleNamespace:
    """Return the process-local parser registry holder."""

    global _WORKER_BUILDER
    if _WORKER_BUILDER is None:
        init_parse_worker()
    assert _WORKER_BUILDER is not None
    return _WORKER_BUILDER


def parse_file_in_worker(
    repo_path_str: str,
    file_path_str: str,
    is_dependency: bool,
) -> dict[str, Any]:
    """Parse one repository file inside a process-pool worker."""

    return parse_file(
        _worker_builder(),
        Path(repo_path_str),
        Path(file_path_str),
        is_dependency,
        get_config_value_fn=get_config_value,
        debug_log_fn=lambda *_args, **_kwargs: None,
        error_logger_fn=error_logger,
        warning_logger_fn=warning_logger,
    )


__all__ = ["init_parse_worker", "parse_file_in_worker"]
