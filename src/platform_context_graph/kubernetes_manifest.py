"""Shared Kubernetes manifest helpers used outside parser-only modules."""

from __future__ import annotations

from typing import Any


def has_k8s_api_version(api_version: str | None) -> bool:
    """Return whether the document declares any Kubernetes-style API version."""

    return bool(api_version)


def extract_container_images(doc: dict[str, Any]) -> list[str]:
    """Extract workload container images from a Kubernetes-style manifest."""

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
    """Parse one generic Kubernetes-style resource into runtime metadata."""

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
    if kind == "HTTPRoute":
        backends = _extract_httproute_backends(doc)
        if backends:
            node["backend_refs"] = ",".join(backends)
    return node


def _extract_httproute_backends(doc: dict[str, Any]) -> list[str]:
    """Extract backend service names from an HTTPRoute spec."""

    backends: list[str] = []
    spec = doc.get("spec", {}) or {}
    for rule in spec.get("rules", []) or []:
        if not isinstance(rule, dict):
            continue
        for ref in rule.get("backendRefs", []) or []:
            if isinstance(ref, dict) and ref.get("name"):
                backends.append(ref["name"])
    return backends
