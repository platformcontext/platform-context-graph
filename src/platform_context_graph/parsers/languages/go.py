"""Go tree-sitter parser compatibility facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .go_sql_support import extract_go_embedded_sql_queries
from .go_support import parse_go_file, pre_scan_go


class GoTreeSitterParser:
    """Parse Go source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Initialize the parser facade.

        Args:
            generic_parser_wrapper: Wrapper object providing parser and language.
        """
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = generic_parser_wrapper.language_name
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def parse(
        self, path: Path, is_dependency: bool = False, index_source: bool = False
    ) -> Dict[str, Any]:
        """Parse one Go file."""
        result = parse_go_file(
            self, path, is_dependency=is_dependency, index_source=index_source
        )
        result["embedded_sql_queries"] = extract_go_embedded_sql_queries(path)
        return result


__all__ = ["GoTreeSitterParser", "pre_scan_go"]
