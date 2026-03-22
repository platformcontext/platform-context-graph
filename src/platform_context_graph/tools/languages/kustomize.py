"""Kustomize-specific YAML manifest classification and parsing."""

from typing import Any

_KUSTOMIZE_API = "kustomize.config.k8s.io/"


def is_kustomization(api_version: str | None, kind: str | None, filename: str) -> bool:
    """Return whether the document or filename describes a Kustomize overlay.

    Args:
        api_version: Resource API version.
        kind: Resource kind.
        filename: Basename of the YAML file.

    Returns:
        ``True`` when the resource should be parsed as a Kustomization.
    """
    if api_version and api_version.startswith(_KUSTOMIZE_API):
        return True
    if kind == "Kustomization" and (api_version or "").startswith("kustomize"):
        return True
    return filename.lower() in ("kustomization.yaml", "kustomization.yml")


def parse_kustomization(
    doc: dict[str, Any],
    path: str,
    line_number: int,
    language_name: str,
) -> dict[str, Any]:
    """Parse a Kustomize overlay resource.

    Args:
        doc: Parsed YAML document.
        path: Source file path.
        line_number: 1-based document start line.
        language_name: Language name to include in the result.

    Returns:
        Parsed Kustomize overlay metadata.
    """
    patch_paths = [
        patch["path"]
        for patch in doc.get("patches", []) or []
        if isinstance(patch, dict) and "path" in patch
    ]
    return {
        "name": "kustomization",
        "line_number": line_number,
        "namespace": doc.get("namespace", ""),
        "resources": doc.get("resources", []) or [],
        "patches": patch_paths,
        "path": path,
        "lang": language_name,
    }
