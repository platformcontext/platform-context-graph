"""Dockerfile tree-sitter parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .dockerfile_support import parse_dockerfile_tree


class DockerfileTreeSitterParser:
    """Parse Dockerfiles into structured build/runtime metadata."""

    def __init__(self, generic_parser_wrapper: Any):
        """Bind a tree-sitter wrapper to the Dockerfile parser facade."""

        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "dockerfile"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser

    def parse(
        self,
        path: Path,
        is_dependency: bool = False,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Parse one Dockerfile into structured entities plus searchable content."""

        source_bytes = path.read_bytes()
        tree = self.parser.parse(source_bytes)
        extracted = parse_dockerfile_tree(tree.root_node, source_bytes)
        result = {
            "path": str(path),
            "lang": "dockerfile",
            "is_dependency": is_dependency,
            "functions": [],
            "classes": [],
            "imports": [],
            "function_calls": [],
            "variables": [],
            "modules": [],
            "module_inclusions": [],
            **extracted,
        }
        if index_source:
            result["source"] = source_bytes.decode("utf-8", "ignore")
        return result


__all__ = ["DockerfileTreeSitterParser"]
