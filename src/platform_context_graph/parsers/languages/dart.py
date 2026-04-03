"""Dart tree-sitter parser compatibility facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import dart_support as _dart_support
from .dart_support import DART_QUERIES, parse_dart_file, pre_scan_dart

_dart_support.DART_QUERIES = DART_QUERIES


class DartTreeSitterParser:
    """Parse Dart source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Initialize the parser facade.

        Args:
            generic_parser_wrapper: Wrapper object providing parser and language.
        """

        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "dart"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def parse(
        self,
        path: Path,
        is_dependency: bool = False,
        index_source: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """Parse one Dart file."""

        del kwargs
        return parse_dart_file(
            self, path, is_dependency=is_dependency, index_source=index_source
        )


__all__ = ["DartTreeSitterParser", "pre_scan_dart"]
