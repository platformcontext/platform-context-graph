"""Targeted parser for high-signal JSON config files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...utils.tree_sitter_manager import get_tree_sitter_manager
from .json_config_support import (
    apply_json_document,
    build_empty_result,
    normalize_json_source,
)


class JSONConfigTreeSitterParser:
    """Parse selected JSON config files into graph-friendly entities."""

    def __init__(self, generic_parser_wrapper: Any) -> None:
        """Bind to a shared wrapper or create a standalone JSON parser."""

        if isinstance(generic_parser_wrapper, str):
            manager = get_tree_sitter_manager()
            self.language_name = generic_parser_wrapper
            self.language = manager.get_language_safe(self.language_name)
            self.parser = manager.create_parser(self.language_name)
            self.generic_parser_wrapper = None
            return

        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = generic_parser_wrapper.language_name
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser

    def parse(
        self,
        path: Path | str,
        is_dependency: bool = False,
        *,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Parse one JSON file into targeted config entities."""

        file_path = Path(path)
        source_text = file_path.read_text(encoding="utf-8")
        result = build_empty_result(str(file_path), self.language_name, is_dependency)
        normalized_source = normalize_json_source(source_text, filename=file_path.name)
        if not normalized_source:
            if index_source:
                result["source"] = source_text
            return result

        document = json.loads(normalized_source)
        apply_json_document(
            result,
            document,
            filename=file_path.name,
            language_name=self.language_name,
        )
        if index_source:
            result["source"] = source_text
        return result


__all__ = ["JSONConfigTreeSitterParser"]
