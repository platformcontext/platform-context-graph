"""Groovy tree-sitter parser with Jenkins-focused metadata extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .groovy_support import extract_jenkins_pipeline_metadata


class GroovyTreeSitterParser:
    """Parse Groovy files into searchable Jenkins-aware metadata."""

    def __init__(self, generic_parser_wrapper: Any):
        """Bind a tree-sitter wrapper to the Groovy parser facade."""

        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "groovy"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser

    def parse(
        self,
        path: Path,
        is_dependency: bool = False,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Parse one Groovy file into minimal entities plus Jenkins metadata."""

        source_bytes = path.read_bytes()
        self.parser.parse(source_bytes)
        source_text = source_bytes.decode("utf-8", "ignore")
        result = {
            "path": str(path),
            "lang": "groovy",
            "is_dependency": is_dependency,
            "functions": [],
            "classes": [],
            "imports": [],
            "function_calls": [],
            "variables": [],
            "modules": [],
            "module_inclusions": [],
            **extract_jenkins_pipeline_metadata(source_text),
        }
        if index_source:
            result["source"] = source_text
        return result


__all__ = ["GroovyTreeSitterParser"]
