"""Crossplane-specific YAML manifest classification and parsing."""

import re
from typing import Any

_CROSSPLANE_XRD_API = "apiextensions.crossplane.io/"
_CROSSPLANE_CLAIM_PATTERN = re.compile(r"^[a-z0-9.-]+\.crossplane\.io/")


def is_crossplane_xrd(api_version: str, kind: str) -> bool:
    """Return whether the document is a Crossplane XRD.

    Args:
        api_version: Resource API version.
        kind: Resource kind.

    Returns:
        ``True`` when the resource is a Crossplane XRD.
    """
    return (
        api_version.startswith(_CROSSPLANE_XRD_API)
        and kind == "CompositeResourceDefinition"
    )


def is_crossplane_composition(api_version: str, kind: str) -> bool:
    """Return whether the document is a Crossplane Composition.

    Args:
        api_version: Resource API version.
        kind: Resource kind.

    Returns:
        ``True`` when the resource is a Crossplane Composition.
    """
    return api_version.startswith(_CROSSPLANE_XRD_API) and kind == "Composition"


def is_crossplane_claim(api_version: str, kind: str) -> bool:
    """Return whether the document is a Crossplane claim resource.

    Args:
        api_version: Resource API version.
        kind: Resource kind.

    Returns:
        ``True`` when the resource matches the Crossplane claim pattern.
    """
    del kind
    if api_version.startswith(_CROSSPLANE_XRD_API):
        return False
    if api_version.startswith("pkg.crossplane.io/"):
        return False
    return bool(_CROSSPLANE_CLAIM_PATTERN.match(api_version))


def parse_crossplane_xrd(
    doc: dict[str, Any],
    metadata: dict[str, Any],
    path: str,
    line_number: int,
    language_name: str,
) -> dict[str, Any]:
    """Parse a Crossplane CompositeResourceDefinition.

    Args:
        doc: Parsed YAML document.
        metadata: Resource metadata.
        path: Source file path.
        line_number: 1-based document start line.
        language_name: Language name to include in the result.

    Returns:
        Parsed Crossplane XRD metadata.
    """
    spec = doc.get("spec", {}) or {}
    names = spec.get("names", {}) or {}
    claim_names = spec.get("claimNames", {}) or {}
    return {
        "name": metadata.get("name", ""),
        "line_number": line_number,
        "group": spec.get("group", ""),
        "kind": names.get("kind", ""),
        "plural": names.get("plural", ""),
        "claim_kind": claim_names.get("kind", ""),
        "claim_plural": claim_names.get("plural", ""),
        "path": path,
        "lang": language_name,
    }


def parse_crossplane_composition(
    doc: dict[str, Any],
    metadata: dict[str, Any],
    path: str,
    line_number: int,
    language_name: str,
) -> dict[str, Any]:
    """Parse a Crossplane Composition.

    Args:
        doc: Parsed YAML document.
        metadata: Resource metadata.
        path: Source file path.
        line_number: 1-based document start line.
        language_name: Language name to include in the result.

    Returns:
        Parsed Crossplane Composition metadata.
    """
    spec = doc.get("spec", {}) or {}
    composite_ref = spec.get("compositeTypeRef", {}) or {}
    resources_raw = spec.get("resources", []) or []
    resource_names = [
        resource["name"]
        for resource in resources_raw
        if isinstance(resource, dict) and "name" in resource
    ]

    return {
        "name": metadata.get("name", ""),
        "line_number": line_number,
        "composite_api_version": composite_ref.get("apiVersion", ""),
        "composite_kind": composite_ref.get("kind", ""),
        "resource_count": len(resources_raw),
        "resource_names": ",".join(resource_names),
        "path": path,
        "lang": language_name,
    }


def parse_crossplane_claim(
    metadata: dict[str, Any],
    api_version: str,
    kind: str,
    path: str,
    line_number: int,
    language_name: str,
) -> dict[str, Any]:
    """Parse a Crossplane claim resource.

    Args:
        metadata: Resource metadata.
        api_version: Resource API version.
        kind: Resource kind.
        path: Source file path.
        line_number: 1-based document start line.
        language_name: Language name to include in the result.

    Returns:
        Parsed Crossplane claim metadata.
    """
    return {
        "name": metadata.get("name", ""),
        "line_number": line_number,
        "kind": kind,
        "api_version": api_version,
        "namespace": metadata.get("namespace", ""),
        "path": path,
        "lang": language_name,
    }
