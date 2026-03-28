"""Utilities for reading source files from mixed-encoding repositories."""

from __future__ import annotations

import os
from pathlib import Path


def read_source_text(path: Path, *, preferred_encoding: str = "utf-8") -> str:
    """Return decoded source text with pragmatic fallbacks for legacy files.

    Args:
        path: Source file to read.
        preferred_encoding: Primary encoding to try first.

    Returns:
        Decoded text content for the file.
    """

    _ensure_source_size_within_limit(path)
    payload = path.read_bytes()
    for encoding in (preferred_encoding, "cp1252", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode(preferred_encoding, errors="ignore")


def _ensure_source_size_within_limit(path: Path) -> None:
    """Reject oversized source files before loading them fully into memory."""

    max_bytes = _resolve_max_source_bytes()
    if max_bytes is None:
        return

    file_size = path.stat().st_size
    if file_size <= max_bytes:
        return

    raise ValueError(
        f"Source file {path} exceeds configured maximum size "
        f"({file_size} > {max_bytes} bytes)"
    )


def _resolve_max_source_bytes() -> int | None:
    """Return the configured source-file size ceiling in bytes, when set."""

    configured = os.getenv("MAX_FILE_SIZE_MB")
    if configured is None:
        try:
            from ..cli.config_manager import get_config_value
        except Exception:
            configured = None
        else:
            configured = get_config_value("MAX_FILE_SIZE_MB")

    if configured in (None, ""):
        return None

    try:
        max_megabytes = int(configured)
    except ValueError:
        return None
    if max_megabytes <= 0:
        return None
    return max_megabytes * 1024 * 1024
