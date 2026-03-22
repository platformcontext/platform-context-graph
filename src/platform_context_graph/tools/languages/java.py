"""Java tree-sitter parser compatibility facade."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

from platform_context_graph.utils.debug_log import error_logger

from .java_support import parse_java_file


class JavaTreeSitterParser:
    """Parse Java source files with tree-sitter."""

    def __init__(self, generic_parser_wrapper: Any):
        """Initialize the parser facade.

        Args:
            generic_parser_wrapper: Wrapper object providing the parser and language.
        """
        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = "java"
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser
        self.index_source = False

    def parse(
        self, path: Path, is_dependency: bool = False, index_source: bool = False
    ) -> Dict[str, Any]:
        """Parse one Java file.

        Args:
            path: File to parse.
            is_dependency: Whether the file came from dependency indexing.
            index_source: Whether to include source text in the parse output.

        Returns:
            A normalized parsed-file dictionary.
        """
        return parse_java_file(
            self, path, is_dependency=is_dependency, index_source=index_source
        )


def pre_scan_java(files: list[Path], parser_wrapper: Any) -> dict[str, list[str]]:
    """Scan Java files for top-level names and map them to file paths."""
    name_to_files: dict[str, list[str]] = {}

    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()

            for match in re.finditer(
                r"\b(?:public\s+|private\s+|protected\s+)?(?:static\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)",
                content,
            ):
                class_name = match.group(1)
                name_to_files.setdefault(class_name, []).append(str(path))

            for match in re.finditer(
                r"\b(?:public\s+|private\s+|protected\s+)?interface\s+(\w+)",
                content,
            ):
                interface_name = match.group(1)
                name_to_files.setdefault(interface_name, []).append(str(path))
        except Exception as exc:
            error_logger(f"Error pre-scanning Java file {path}: {exc}")

    del parser_wrapper
    return name_to_files


def _find_annotations(tree: Any) -> list[dict[str, Any]]:
    """Detect annotation declarations in a parsed Java tree."""
    annotations: list[dict[str, Any]] = []
    for node in tree.find_all("annotation_type_declaration"):
        name = node.child_by_field_name("name").text
        annotations.append(
            {"type": "Annotation", "name": name, "location": node.start_point}
        )
    return annotations


def _find_applied_annotations(tree: Any) -> list[dict[str, Any]]:
    """Detect annotation usages in a parsed Java tree."""
    applied: list[dict[str, Any]] = []
    for node in tree.find_all("marker_annotation"):
        name = node.child_by_field_name("name").text
        applied.append(
            {"type": "AnnotationUsage", "name": name, "location": node.start_point}
        )
    return applied


__all__ = ["JavaTreeSitterParser", "pre_scan_java"]
