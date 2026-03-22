"""Utilities for reading source files from mixed-encoding repositories."""

from __future__ import annotations

from pathlib import Path


def read_source_text(path: Path, *, preferred_encoding: str = "utf-8") -> str:
    """Return decoded source text with pragmatic fallbacks for legacy files.

    Args:
        path: Source file to read.
        preferred_encoding: Primary encoding to try first.

    Returns:
        Decoded text content for the file.
    """

    payload = path.read_bytes()
    for encoding in (preferred_encoding, "cp1252", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode(preferred_encoding, errors="ignore")
