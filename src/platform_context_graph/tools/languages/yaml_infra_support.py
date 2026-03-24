"""Generic helpers for the handwritten YAML infrastructure parser."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ...utils.debug_log import warning_logger


class _PermissiveSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that preserves unknown tagged values."""


def _construct_unknown_tag(
    loader: _PermissiveSafeLoader,
    tag_suffix: str,
    node: yaml.Node,
) -> Any:
    """Construct an unknown YAML tag using the underlying node shape."""

    del tag_suffix
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


_PermissiveSafeLoader.add_multi_constructor("", _construct_unknown_tag)

_JINJA_EXPR_PLACEHOLDER = "__PCG_JINJA_EXPR__"
_JINJA_CONTROL_PREFIXES = ("{%", "{%-", "{#")
_JINJA_CONTROL_SUFFIXES = ("%}", "-%}", "#}")
_JINJA_MAPPING_EXPR_RE = re.compile(
    r"(^\s*[^#\n][^:\n]*:\s*)(\{\{.*\}\})(\s*(?:#.*)?)$"
)
_JINJA_SEQUENCE_EXPR_RE = re.compile(
    r"(^\s*-\s*)(\{\{.*\}\})(\s*(?:#.*)?)$"
)


def _load_all_yaml_documents(content: str) -> list[Any]:
    """Load YAML documents with permissive tag handling."""

    return list(yaml.load_all(content, Loader=_PermissiveSafeLoader))


def _load_yaml_document(content: str) -> Any:
    """Load a single YAML document with permissive tag handling."""

    return yaml.load(content, Loader=_PermissiveSafeLoader)


def _is_jinja_control_line(line: str) -> bool:
    """Return whether a line is a standalone Jinja control/comment line."""

    stripped = line.strip()
    return stripped.startswith(_JINJA_CONTROL_PREFIXES)


def _sanitize_jinja_templated_yaml(content: str) -> str | None:
    """Strip Jinja control blocks and normalize expression-only scalar values."""

    if not any(marker in content for marker in ("{%", "{#", "{{")):
        return None

    sanitized_lines: list[str] = []
    in_control_block = False
    block_suffix = ""
    changed = False
    for line in content.splitlines():
        stripped = line.strip()
        if in_control_block:
            changed = True
            if block_suffix and block_suffix in stripped:
                in_control_block = False
                block_suffix = ""
            continue
        if _is_jinja_control_line(line):
            changed = True
            if not any(suffix in stripped for suffix in _JINJA_CONTROL_SUFFIXES):
                block_suffix = "#}" if stripped.startswith("{#") else "%}"
                in_control_block = True
            continue
        updated_line = _JINJA_MAPPING_EXPR_RE.sub(
            lambda match: (
                f'{match.group(1)}"{_JINJA_EXPR_PLACEHOLDER}"{match.group(3)}'
            ),
            line,
        )
        updated_line = _JINJA_SEQUENCE_EXPR_RE.sub(
            lambda match: (
                f'{match.group(1)}"{_JINJA_EXPR_PLACEHOLDER}"{match.group(3)}'
            ),
            updated_line,
        )
        if updated_line != line:
            changed = True
        sanitized_lines.append(updated_line)
    if not changed:
        return None
    return "\n".join(sanitized_lines) + "\n"


def _load_all_yaml_with_fallbacks(content: str) -> list[Any]:
    """Load YAML documents while tolerating tabs and Jinja-templated control lines."""

    tried_variants = [content]
    if "\t" in content:
        tried_variants.append(content.expandtabs(2))
    sanitized = _sanitize_jinja_templated_yaml(content)
    if sanitized is not None:
        tried_variants.append(sanitized)
        if "\t" in sanitized:
            tried_variants.append(sanitized.expandtabs(2))

    last_error: yaml.YAMLError | None = None
    seen: set[str] = set()
    for candidate in tried_variants:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return _load_all_yaml_documents(candidate)
        except yaml.YAMLError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return []


def _load_yaml_with_fallbacks(content: str) -> Any:
    """Load a single YAML document while tolerating templated YAML patterns."""

    tried_variants = [content]
    if "\t" in content:
        tried_variants.append(content.expandtabs(2))
    sanitized = _sanitize_jinja_templated_yaml(content)
    if sanitized is not None:
        tried_variants.append(sanitized)
        if "\t" in sanitized:
            tried_variants.append(sanitized.expandtabs(2))

    last_error: yaml.YAMLError | None = None
    seen: set[str] = set()
    for candidate in tried_variants:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return _load_yaml_document(candidate)
        except yaml.YAMLError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return None


def build_empty_result(
    path: str,
    language_name: str,
    is_dependency: bool,
) -> dict[str, Any]:
    """Create the standard empty parse result for YAML infrastructure files.

    Args:
        path: Source file path.
        language_name: Language name reported in the result.
        is_dependency: Whether the file belongs to dependency code.

    Returns:
        Empty parse result with all expected resource buckets.
    """
    return {
        "path": path,
        "lang": language_name,
        "is_dependency": is_dependency,
        "functions": [],
        "classes": [],
        "imports": [],
        "function_calls": [],
        "variables": [],
        "k8s_resources": [],
        "argocd_applications": [],
        "argocd_applicationsets": [],
        "crossplane_xrds": [],
        "crossplane_compositions": [],
        "crossplane_claims": [],
        "kustomize_overlays": [],
        "helm_charts": [],
        "helm_values": [],
        "cloudformation_resources": [],
        "cloudformation_parameters": [],
        "cloudformation_outputs": [],
    }


def safe_load_all(content: str) -> list[Any]:
    """Load all YAML documents from a string.

    Args:
        content: YAML file content.

    Returns:
        Parsed documents, or an empty list when parsing fails.
    """
    try:
        return _load_all_yaml_with_fallbacks(content)
    except yaml.YAMLError as exc:
        warning_logger(f"YAML parse error: {exc}")
        return []


def compute_doc_line_offsets(content: str) -> list[int]:
    """Compute 1-based start lines for each YAML document in a file.

    Args:
        content: YAML file content.

    Returns:
        Starting line number for each document.
    """
    offsets = [1]
    for line_number, line in enumerate(content.splitlines(), start=1):
        if line.strip() == "---":
            offsets.append(line_number + 1)
    return offsets


def load_yaml_dict(file_path: Path, context_name: str) -> dict[str, Any] | None:
    """Load a single-document YAML file when it should contain a mapping.

    Args:
        file_path: YAML file path to load.
        context_name: Human-readable context used in warning logs.

    Returns:
        Parsed mapping, or ``None`` when loading fails or the document is not a map.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        document = _load_yaml_with_fallbacks(content)
    except (OSError, yaml.YAMLError) as exc:
        warning_logger(f"Cannot parse {context_name}: {exc}")
        return None

    if not isinstance(document, dict):
        return None
    return document
