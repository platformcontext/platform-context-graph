"""SQL tree-sitter parser compatibility facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .sql_support import parse_sql_file


class SQLTreeSitterParser:
    """Parse SQL source files with tree-sitter-backed helpers."""

    def __init__(self, generic_parser_wrapper: Any):
        """Store the generic parser wrapper for later parse operations."""

        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = generic_parser_wrapper.language_name
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser

    def parse(
        self,
        path: Path | str,
        is_dependency: bool = False,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Parse one SQL file into the normalized PCG payload structure."""

        return parse_sql_file(
            self,
            path,
            is_dependency=is_dependency,
            index_source=index_source,
        )


__all__ = ["SQLTreeSitterParser"]
