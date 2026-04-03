"""Helpers for targeted JSON config extraction."""

from __future__ import annotations

import re
from typing import Any

from .cloudformation import is_cloudformation_template, parse_cloudformation_template

_NOISY_JSON_FILENAMES = frozenset(
    {
        "package-lock.json",
        "composer.lock",
    }
)

_HELM_DIRECTIVE_LINE = re.compile(r"^\s*\{\{[-#]?(?:.|\n)*?[-#]?\}\}\s*$")


def build_empty_result(
    path: str, language_name: str, is_dependency: bool
) -> dict[str, Any]:
    """Return the standard parse result shape for targeted JSON parsing."""

    return {
        "path": path,
        "lang": language_name,
        "is_dependency": is_dependency,
        "functions": [],
        "classes": [],
        "imports": [],
        "function_calls": [],
        "variables": [],
        "modules": [],
        "module_inclusions": [],
        "cloudformation_resources": [],
        "cloudformation_parameters": [],
        "cloudformation_outputs": [],
        "json_metadata": {"top_level_keys": []},
    }


def should_skip_json_entities(filename: str) -> bool:
    """Return whether a JSON filename should stay metadata-only."""

    lowered = filename.lower()
    return lowered in _NOISY_JSON_FILENAMES or lowered.endswith(".min.json")


def normalize_json_source(source_text: str) -> str:
    """Normalize JSON text for known real-world config preambles.

    The targeted JSON parser stays strict for document content, but some repos
    legitimately store JSON documents behind a small Helm-templated preamble.
    We strip only leading full-line Helm directives and otherwise leave the
    document untouched. Empty or whitespace-only files normalize to ``""``.
    """

    stripped = source_text.lstrip("\ufeff")
    if not stripped.strip():
        return ""

    lines = stripped.splitlines()
    start_index = 0
    while start_index < len(lines) and _HELM_DIRECTIVE_LINE.match(lines[start_index]):
        start_index += 1
    return "\n".join(lines[start_index:]).lstrip()


def apply_json_document(
    result: dict[str, Any],
    document: Any,
    *,
    filename: str,
    language_name: str,
) -> None:
    """Populate one parse result with targeted JSON extraction."""

    if not isinstance(document, dict):
        return

    result["json_metadata"] = {"top_level_keys": list(document.keys())}
    if is_cloudformation_template(document):
        result.update(
            parse_cloudformation_template(document, result["path"], 1, language_name)
        )
        return

    if should_skip_json_entities(filename):
        return

    lowered = filename.lower()
    if lowered == "package.json":
        result["variables"].extend(_dependency_variables(document, language_name))
        result["functions"].extend(_script_functions(document, language_name))
        return

    if lowered == "composer.json":
        result["variables"].extend(
            _composer_dependency_variables(document, language_name)
        )
        return

    if lowered == "tsconfig.json":
        result["variables"].extend(_tsconfig_variables(document, language_name))


def _dependency_variables(
    document: dict[str, Any], language_name: str
) -> list[dict[str, Any]]:
    """Return package.json dependency variables."""

    rows: list[dict[str, Any]] = []
    line_number = 1
    for section in ("dependencies", "devDependencies"):
        section_values = document.get(section)
        if not isinstance(section_values, dict):
            continue
        for name, value in section_values.items():
            rows.append(
                {
                    "name": str(name),
                    "line_number": line_number,
                    "value": str(value),
                    "section": section,
                    "config_kind": "dependency",
                    "package_manager": "npm",
                    "lang": language_name,
                }
            )
            line_number += 1
    return rows


def _script_functions(
    document: dict[str, Any], language_name: str
) -> list[dict[str, Any]]:
    """Return package.json scripts as lightweight function nodes."""

    scripts = document.get("scripts")
    if not isinstance(scripts, dict):
        return []

    rows: list[dict[str, Any]] = []
    line_number = 1
    for name, command in scripts.items():
        rows.append(
            {
                "name": str(name),
                "line_number": line_number,
                "end_line": line_number,
                "args": [],
                "cyclomatic_complexity": 1,
                "source": str(command),
                "function_kind": "json_script",
                "context": "scripts",
                "context_type": "json",
                "lang": language_name,
            }
        )
        line_number += 1
    return rows


def _composer_dependency_variables(
    document: dict[str, Any], language_name: str
) -> list[dict[str, Any]]:
    """Return composer.json dependency variables."""

    rows: list[dict[str, Any]] = []
    line_number = 1
    for section in ("require", "require-dev"):
        section_values = document.get(section)
        if not isinstance(section_values, dict):
            continue
        for name, value in section_values.items():
            rows.append(
                {
                    "name": str(name),
                    "line_number": line_number,
                    "value": str(value),
                    "section": section,
                    "config_kind": "dependency",
                    "package_manager": "composer",
                    "lang": language_name,
                }
            )
            line_number += 1
    return rows


def _tsconfig_variables(
    document: dict[str, Any], language_name: str
) -> list[dict[str, Any]]:
    """Return targeted tsconfig metadata as variable nodes."""

    rows: list[dict[str, Any]] = []
    line_number = 1

    extends_value = document.get("extends")
    if isinstance(extends_value, str):
        rows.append(
            {
                "name": "extends",
                "line_number": line_number,
                "value": extends_value,
                "section": "extends",
                "config_kind": "extends",
                "lang": language_name,
            }
        )
        line_number += 1

    references = document.get("references")
    if isinstance(references, list):
        for item in references:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            reference_path = item["path"]
            rows.append(
                {
                    "name": f"reference:{reference_path}",
                    "line_number": line_number,
                    "value": reference_path,
                    "section": "references",
                    "config_kind": "reference",
                    "lang": language_name,
                }
            )
            line_number += 1

    compiler_options = document.get("compilerOptions")
    if isinstance(compiler_options, dict):
        paths = compiler_options.get("paths")
        if isinstance(paths, dict):
            for alias, values in paths.items():
                if isinstance(values, list):
                    normalized = ",".join(str(value) for value in values)
                else:
                    normalized = str(values)
                rows.append(
                    {
                        "name": f"path:{alias}",
                        "line_number": line_number,
                        "value": normalized,
                        "section": "compilerOptions.paths",
                        "config_kind": "path",
                        "lang": language_name,
                    }
                )
                line_number += 1

    return rows


__all__ = [
    "apply_json_document",
    "build_empty_result",
    "normalize_json_source",
    "should_skip_json_entities",
]
