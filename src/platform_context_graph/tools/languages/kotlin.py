"""Compatibility facade for the handwritten Kotlin parser."""

from .kotlin_support import (  # noqa: F401
    KOTLIN_QUERIES,
    KotlinTreeSitterParser,
    parse_kotlin_file,
    pre_scan_kotlin,
)

__all__ = [
    "KOTLIN_QUERIES",
    "KotlinTreeSitterParser",
    "parse_kotlin_file",
    "pre_scan_kotlin",
]
