"""Helpers for targeted JSON config extraction."""

from __future__ import annotations

import re
from typing import Any

from .cloudformation import is_cloudformation_template, parse_cloudformation_template
from .json_data_intelligence_support import (
    apply_bi_replay_document,
    apply_dbt_manifest_document,
    apply_governance_replay_document,
    apply_quality_replay_document,
    apply_semantic_replay_document,
    apply_warehouse_replay_document,
    is_bi_replay_document,
    is_dbt_manifest_document,
    is_governance_replay_document,
    is_quality_replay_document,
    is_semantic_replay_document,
    is_warehouse_replay_document,
)

_NOISY_JSON_FILENAMES = frozenset(
    {
        "package-lock.json",
        "composer.lock",
    }
)

_HELM_DIRECTIVE_LINE = re.compile(r"^\s*\{\{[-#]?(?:.|\n)*?[-#]?\}\}\s*$")


def is_typescript_config_filename(filename: str) -> bool:
    """Return whether a filename belongs to the tsconfig JSON family."""

    lowered = filename.lower()
    return lowered.startswith("tsconfig") and lowered.endswith(".json")


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
        "analytics_models": [],
        "data_assets": [],
        "data_columns": [],
        "query_executions": [],
        "dashboard_assets": [],
        "data_quality_checks": [],
        "data_owners": [],
        "data_contracts": [],
        "data_relationships": [],
        "data_governance_annotations": [],
        "data_intelligence_coverage": {
            "confidence": 0.0,
            "state": "unavailable",
            "unresolved_references": [],
        },
        "json_metadata": {"top_level_keys": []},
    }


def should_skip_json_entities(filename: str) -> bool:
    """Return whether a JSON filename should stay metadata-only."""

    lowered = filename.lower()
    return lowered in _NOISY_JSON_FILENAMES or lowered.endswith(".min.json")


def normalize_json_source(source_text: str, *, filename: str | None = None) -> str:
    """Normalize JSON text for known real-world config preambles.

    The targeted JSON parser stays strict for document content, but some repos
    legitimately store JSON documents behind a small Helm-templated preamble.
    We strip only leading full-line Helm directives and otherwise leave the
    document untouched except for ``tsconfig*.json`` files, where we also strip
    JSONC comments and trailing commas. Empty or whitespace-only files
    normalize to ``""``.
    """

    stripped = source_text.lstrip("\ufeff")
    if not stripped.strip():
        return ""

    lines = stripped.splitlines()
    start_index = 0
    while start_index < len(lines) and _HELM_DIRECTIVE_LINE.match(lines[start_index]):
        start_index += 1
    normalized = "\n".join(lines[start_index:]).lstrip()
    if filename and is_typescript_config_filename(filename):
        return _strip_trailing_commas(_strip_jsonc_comments(normalized))
    return normalized


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
    if is_dbt_manifest_document(document, filename=filename):
        apply_dbt_manifest_document(result, document)
        return
    if is_warehouse_replay_document(document, filename=filename):
        apply_warehouse_replay_document(result, document)
        return
    if is_bi_replay_document(document, filename=filename):
        apply_bi_replay_document(result, document)
        return
    if is_semantic_replay_document(document, filename=filename):
        apply_semantic_replay_document(result, document)
        return
    if is_quality_replay_document(document, filename=filename):
        apply_quality_replay_document(result, document)
        return
    if is_governance_replay_document(document, filename=filename):
        apply_governance_replay_document(result, document)
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

    if is_typescript_config_filename(lowered):
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


def _strip_jsonc_comments(source_text: str) -> str:
    """Strip JSONC comments while preserving string literals."""

    result: list[str] = []
    index = 0
    in_string = False
    in_line_comment = False
    in_block_comment = False
    escape_next = False

    while index < len(source_text):
        char = source_text[index]
        next_char = source_text[index + 1] if index + 1 < len(source_text) else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                result.append(char)
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                continue
            if char == "\n":
                result.append(char)
            index += 1
            continue

        if in_string:
            result.append(char)
            if escape_next:
                escape_next = False
            elif char == "\\":
                escape_next = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"' and not in_string:
            in_string = True
            result.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue

        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue

        result.append(char)
        index += 1

    return "".join(result)


def _strip_trailing_commas(source_text: str) -> str:
    """Remove commas that appear immediately before JSON closing tokens."""

    result: list[str] = []
    in_string = False
    escape_next = False
    index = 0

    while index < len(source_text):
        char = source_text[index]
        if in_string:
            result.append(char)
            if escape_next:
                escape_next = False
            elif char == "\\":
                escape_next = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue

        if char == ",":
            lookahead = index + 1
            while lookahead < len(source_text) and source_text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(source_text) and source_text[lookahead] in "]}":
                index += 1
                continue

        result.append(char)
        index += 1

    return "".join(result)


__all__ = [
    "apply_json_document",
    "build_empty_result",
    "is_typescript_config_filename",
    "normalize_json_source",
    "should_skip_json_entities",
]
