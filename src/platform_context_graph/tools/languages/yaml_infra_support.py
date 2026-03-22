"""Generic helpers for the handwritten YAML infrastructure parser."""

from pathlib import Path
from typing import Any

import yaml

from ...utils.debug_log import warning_logger


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
    }


def safe_load_all(content: str) -> list[dict[str, Any]]:
    """Load all YAML documents from a string.

    Args:
        content: YAML file content.

    Returns:
        Parsed documents, or an empty list when parsing fails.
    """
    try:
        return list(yaml.safe_load_all(content))
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
        document = yaml.safe_load(content)
    except (OSError, yaml.YAMLError) as exc:
        warning_logger(f"Cannot parse {context_name}: {exc}")
        return None

    if not isinstance(document, dict):
        return None
    return document
