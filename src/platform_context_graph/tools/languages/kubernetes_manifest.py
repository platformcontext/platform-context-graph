"""Kubernetes-style YAML manifest classification and parsing."""

from typing import Any


def has_k8s_api_version(api_version: str | None) -> bool:
    """Return whether the document declares any Kubernetes-style API version.

    Args:
        api_version: Resource API version.

    Returns:
        ``True`` when the document has a non-empty API version.
    """
    return bool(api_version)


def extract_container_images(doc: dict[str, Any]) -> list[str]:
    """Extract container images from workload-style Kubernetes resources.

    Args:
        doc: Parsed YAML document.

    Returns:
        Image references found in containers and initContainers.
    """
    images: list[str] = []
    spec = doc.get("spec", {}) or {}
    template = spec.get("template", {}) or {}
    if not template and spec.get("jobTemplate"):
        job_spec = (spec.get("jobTemplate", {}) or {}).get("spec", {}) or {}
        template = job_spec.get("template", {}) or {}

    pod_spec = template.get("spec", {}) or {}
    for container in pod_spec.get("containers", []) or []:
        if isinstance(container, dict) and container.get("image"):
            images.append(container["image"])
    for container in pod_spec.get("initContainers", []) or []:
        if isinstance(container, dict) and container.get("image"):
            images.append(container["image"])
    return images


def parse_k8s_resource(
    doc: dict[str, Any],
    metadata: dict[str, Any],
    api_version: str,
    kind: str,
    path: str,
    line_number: int,
    language_name: str,
) -> dict[str, Any]:
    """Parse a generic Kubernetes-style resource.

    Args:
        doc: Parsed YAML document.
        metadata: Resource metadata.
        api_version: Resource API version.
        kind: Resource kind.
        path: Source file path.
        line_number: 1-based document start line.
        language_name: Language name to include in the result.

    Returns:
        Parsed Kubernetes-style resource metadata.
    """
    node: dict[str, Any] = {
        "name": metadata.get("name", ""),
        "line_number": line_number,
        "kind": kind,
        "api_version": api_version,
        "namespace": metadata.get("namespace", ""),
        "path": path,
        "lang": language_name,
    }
    annotations = metadata.get("annotations", {}) or {}
    labels = metadata.get("labels", {}) or {}
    if annotations:
        node["annotations"] = str(annotations)
    if labels:
        node["labels"] = str(labels)
    if kind in ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"):
        images = extract_container_images(doc)
        if images:
            node["container_images"] = ",".join(images)
    return node
