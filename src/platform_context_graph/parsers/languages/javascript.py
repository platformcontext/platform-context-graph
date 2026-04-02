"""Compatibility facade for the handwritten JavaScript parser."""

from .javascript_support import (  # noqa: F401
    JS_QUERIES,
    JavascriptTreeSitterParser,
    parse_javascript_file,
    pre_scan_javascript,
)

__all__ = [
    "JS_QUERIES",
    "JavascriptTreeSitterParser",
    "parse_javascript_file",
    "pre_scan_javascript",
]
