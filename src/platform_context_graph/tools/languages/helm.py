"""Helm-specific YAML manifest classification and parsing."""

from pathlib import Path
from typing import Any

from .yaml_infra_support import load_yaml_dict


def is_helm_chart(filename: str) -> bool:
    """Return whether the filename is a Helm chart descriptor.

    Args:
        filename: Basename of the YAML file.

    Returns:
        ``True`` when the file is ``Chart.yaml`` or ``Chart.yml``.
    """
    return filename.lower() in ("chart.yaml", "chart.yml")


def is_helm_values(filename: str) -> bool:
    """Return whether the filename is a Helm values file.

    Args:
        filename: Basename of the YAML file.

    Returns:
        ``True`` when the file name starts with ``values`` and ends in YAML.
    """
    lower = filename.lower()
    return lower.startswith("values") and lower.endswith((".yaml", ".yml"))


def parse_helm_chart(file_path: Path, language_name: str) -> dict[str, Any] | None:
    """Parse a Helm ``Chart.yaml`` file.

    Args:
        file_path: Chart file path.
        language_name: Language name to include in the result.

    Returns:
        Parsed Helm chart metadata, or ``None`` when parsing fails.
    """
    document = load_yaml_dict(file_path, "Chart.yaml")
    if document is None:
        return None

    dependency_names = [
        dependency.get("name", "")
        for dependency in document.get("dependencies", []) or []
        if isinstance(dependency, dict)
    ]
    return {
        "name": document.get("name", ""),
        "line_number": 1,
        "version": document.get("version", ""),
        "app_version": str(document.get("appVersion", "")),
        "chart_type": document.get("type", "application"),
        "description": document.get("description", ""),
        "dependencies": ",".join(dependency_names),
        "path": str(file_path),
        "lang": language_name,
    }


def parse_helm_values(file_path: Path, language_name: str) -> dict[str, Any] | None:
    """Parse a Helm ``values*.yaml`` file.

    Args:
        file_path: Helm values file path.
        language_name: Language name to include in the result.

    Returns:
        Parsed Helm values metadata, or ``None`` when parsing fails.
    """
    document = load_yaml_dict(file_path, "values YAML")
    if document is None:
        return None

    return {
        "name": file_path.stem,
        "line_number": 1,
        "top_level_keys": ",".join(str(key) for key in document.keys()),
        "path": str(file_path),
        "lang": language_name,
    }
