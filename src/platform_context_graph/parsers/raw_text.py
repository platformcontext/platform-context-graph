"""Raw-text parser support for searchable non-code infrastructure files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

DOCKERFILE_PARSER_KEY = "__dockerfile__"
JENKINSFILE_PARSER_KEY = "__jenkinsfile__"
RAW_TEXT_PARSER_EXTENSIONS = frozenset(
    {".j2", ".jinja", ".jinja2", ".tpl", ".tftpl", ".conf", ".cfg", ".cnf"}
)
_CONFIG_EXTENSIONS = {".conf", ".cfg", ".cnf"}
_JINJA_EXTENSIONS = {".j2", ".jinja", ".jinja2"}
_TEMPLATE_EXTENSIONS = {".tpl", ".tftpl"}
_YAML_EXTENSIONS = {".yaml", ".yml"}


class RawTextParser:
    """Minimal parser that enables raw-text content ingestion without entities."""

    def __init__(self, language_name: str = "raw_text") -> None:
        """Store the parser label used in debug logging."""

        self.language_name = language_name

    def parse(
        self,
        path: str | Path,
        is_dependency: bool = False,
        *,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Return a parse payload with no entities and a coarse raw-text language."""

        del index_source
        file_path = Path(path)
        return {
            "path": str(file_path),
            "lang": raw_text_language_for_path(file_path),
            "is_dependency": is_dependency,
            "functions": [],
            "classes": [],
            "imports": [],
            "function_calls": [],
            "variables": [],
            "modules": [],
            "module_inclusions": [],
        }


def register_raw_text_parsers(parsers: dict[str, Any]) -> None:
    """Add raw-text parser entries used for searchable IaC/text artifacts."""

    raw_text_parser = RawTextParser()
    for extension in RAW_TEXT_PARSER_EXTENSIONS:
        parsers.setdefault(extension, raw_text_parser)
    parsers.setdefault(DOCKERFILE_PARSER_KEY, raw_text_parser)
    parsers.setdefault(JENKINSFILE_PARSER_KEY, raw_text_parser)


def parser_key_for_path(path: Path, parsers: Mapping[str, Any]) -> str | None:
    """Return the parser-registry key for one path, including special filenames."""

    suffix = path.suffix.lower()
    if suffix in parsers:
        return suffix
    name = path.name.lower()
    if (
        name == "dockerfile" or name.startswith("dockerfile.")
    ) and DOCKERFILE_PARSER_KEY in parsers:
        return DOCKERFILE_PARSER_KEY
    if (
        name == "jenkinsfile" or name.startswith("jenkinsfile.")
    ) and JENKINSFILE_PARSER_KEY in parsers:
        return JENKINSFILE_PARSER_KEY
    return None


def raw_text_language_for_path(path: Path) -> str:
    """Return a coarse language/category label for raw-text content search."""

    name = path.name.lower()
    suffixes = tuple(suffix.lower() for suffix in path.suffixes)
    if name == "dockerfile" or name.startswith("dockerfile."):
        return "dockerfile"
    if name == "jenkinsfile" or name.startswith("jenkinsfile."):
        return "groovy"
    if _CONFIG_EXTENSIONS.intersection(suffixes):
        if _JINJA_EXTENSIONS.intersection(suffixes) or _TEMPLATE_EXTENSIONS.intersection(
            suffixes
        ):
            return "config_template"
        return "config"
    if _YAML_EXTENSIONS.intersection(suffixes) and _JINJA_EXTENSIONS.intersection(
        suffixes
    ):
        return "yaml_template"
    if _JINJA_EXTENSIONS.intersection(suffixes):
        return "template"
    if _TEMPLATE_EXTENSIONS.intersection(suffixes):
        return "template"
    return "raw_text"


__all__ = [
    "DOCKERFILE_PARSER_KEY",
    "JENKINSFILE_PARSER_KEY",
    "RAW_TEXT_PARSER_EXTENSIONS",
    "RawTextParser",
    "parser_key_for_path",
    "raw_text_language_for_path",
    "register_raw_text_parsers",
]
