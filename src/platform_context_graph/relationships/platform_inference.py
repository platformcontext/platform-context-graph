"""Platform inference helpers for relationship evidence extraction."""

from __future__ import annotations

import re

from .platform_families import (
    infer_runtime_family_kind_from_identifiers,
    infer_terraform_runtime_family_kind,
    lookup_runtime_family,
)

_NON_PLATFORM_IDENTIFIERS = {
    "alerts",
    "current",
    "default",
    "eks",
    "ingress",
    "main",
    "pagerduty",
    "pipeline",
    "private",
    "private-regionless",
    "public",
    "terraform_state",
}
_TERRAFORM_CLUSTER_NAME_RE = re.compile(
    r'\bcluster_name\b\s*=\s*"([^"]+)"', re.IGNORECASE
)
_TERRAFORM_NAME_RE = re.compile(r'\bname\b\s*=\s*"([^"]+)"', re.IGNORECASE)
_GITOPS_EXPLICIT_PLATFORM_KEYS = {
    "destinationClusterName",
    "destinationCluster",
    "clusterName",
    "cluster",
    "cluster_name",
}


def _normalize_token(value: str | None) -> str | None:
    """Return a lower-cased trimmed token or ``None`` when empty."""

    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def infer_terraform_platform_kind(content: str) -> str | None:
    """Infer a Terraform platform kind from portable cluster/module signals."""

    return infer_terraform_runtime_family_kind(content)


def extract_terraform_platform_name(content: str) -> str | None:
    """Extract a stable Terraform platform name from cluster-like fields."""

    for pattern in (_TERRAFORM_CLUSTER_NAME_RE, _TERRAFORM_NAME_RE):
        match = pattern.search(content)
        if not match:
            continue
        candidate = match.group(1).strip()
        if candidate and candidate.lower() not in _NON_PLATFORM_IDENTIFIERS:
            return candidate
    return None


def infer_gitops_platform_kind(
    *, repo_name: str, repo_slug: str | None, content: str
) -> str | None:
    """Infer a platform kind from portable GitOps control-plane signals."""

    hinted_kind = infer_runtime_family_kind_from_identifiers((repo_name, repo_slug))
    if hinted_kind is not None:
        return hinted_kind
    lower_content = content.lower()
    if any(key.lower() in lower_content for key in _GITOPS_EXPLICIT_PLATFORM_KEYS):
        return "kubernetes"
    return None


def infer_gitops_platform_id(
    *,
    repo_name: str,
    repo_slug: str | None,
    content: str,
    platform_name: str,
    environment: str | None = None,
    region: str | None = None,
    locator: str | None = None,
) -> str | None:
    """Build a canonical platform id from GitOps repo metadata and config."""

    platform_kind = infer_gitops_platform_kind(
        repo_name=repo_name,
        repo_slug=repo_slug,
        content=content,
    )
    if platform_kind is None:
        return None
    family = lookup_runtime_family(platform_kind)
    return canonical_platform_id(
        kind=platform_kind,
        provider=family.provider if family is not None else None,
        name=platform_name,
        environment=environment,
        region=region,
        locator=locator,
    )


def canonical_platform_id(
    *,
    kind: str,
    provider: str | None,
    name: str | None,
    environment: str | None,
    region: str | None,
    locator: str | None,
) -> str | None:
    """Build a canonical platform identifier without importing relationships."""

    normalized_kind = _normalize_token(kind)
    normalized_provider = _normalize_token(provider)
    normalized_name = _normalize_token(name)
    normalized_environment = _normalize_token(environment)
    normalized_region = _normalize_token(region)
    normalized_locator = _normalize_token(locator)

    discriminator = normalized_locator or normalized_name
    if discriminator is None and not (
        normalized_environment is not None and normalized_region is not None
    ):
        return None

    return (
        "platform:"
        f"{normalized_kind or 'none'}:"
        f"{normalized_provider or 'none'}:"
        f"{discriminator or 'none'}:"
        f"{normalized_environment or 'none'}:"
        f"{normalized_region or 'none'}"
    )


__all__ = [
    "canonical_platform_id",
    "extract_terraform_platform_name",
    "infer_gitops_platform_id",
    "infer_gitops_platform_kind",
    "infer_terraform_platform_kind",
]
