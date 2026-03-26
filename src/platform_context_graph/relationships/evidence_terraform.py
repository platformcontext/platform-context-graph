"""Terraform and Terragrunt relationship evidence extraction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from ..tools.graph_builder_platforms import (
    extract_terraform_platform_name,
    infer_terraform_platform_kind,
)
from .entities import canonical_platform_id
from .file_evidence_support import (
    CatalogEntry,
    append_evidence_for_candidate,
    append_relationship_evidence,
    is_terraform_file,
    iter_checkout_files,
    read_text,
)
from .models import RelationshipEvidenceFact, RepositoryCheckout

_TERRAFORM_PATTERNS: tuple[tuple[str, str, re.Pattern[str], float, str], ...] = (
    (
        "TERRAFORM_APP_REPO",
        "PROVISIONS_DEPENDENCY_FOR",
        re.compile(r'\bapp_repo\b\s*=\s*"([^"]+)"', re.IGNORECASE),
        0.99,
        "Terraform app_repo points at the target repository",
    ),
    (
        "TERRAFORM_APP_NAME",
        "PROVISIONS_DEPENDENCY_FOR",
        re.compile(r'\bapp_name\b\s*=\s*"([^"]+)"', re.IGNORECASE),
        0.94,
        "Terraform app_name matches the target repository name",
    ),
    (
        "TERRAFORM_API_CONFIGURATION",
        "PROVISIONS_DEPENDENCY_FOR",
        re.compile(r'api_configuration\[\s*"([^"]+)"\s*\]', re.IGNORECASE),
        0.95,
        "Terraform api_configuration key matches the target repository name",
    ),
    (
        "TERRAFORM_CLOUDMAP_SERVICE",
        "PROVISIONS_DEPENDENCY_FOR",
        re.compile(r'cloudmap_service\b[^\n"]*?/([A-Za-z0-9._-]+)', re.IGNORECASE),
        0.93,
        "Terraform Cloud Map service references the target repository name",
    ),
    (
        "TERRAFORM_CONFIG_PATH",
        "PROVISIONS_DEPENDENCY_FOR",
        re.compile(r"/(?:configd|api)/([A-Za-z0-9._-]+)/", re.IGNORECASE),
        0.9,
        "Terraform configuration path references the target repository name",
    ),
    (
        "TERRAFORM_GITHUB_REPOSITORY",
        "PROVISIONS_DEPENDENCY_FOR",
        re.compile(
            r"github\.com[:/][^/\"'\s]+/([A-Za-z0-9._-]+)(?:\.git)?",
            re.IGNORECASE,
        ),
        0.98,
        "Terraform GitHub reference points at the target repository",
    ),
    (
        "TERRAFORM_GITHUB_ACTIONS_REPOSITORY",
        "PROVISIONS_DEPENDENCY_FOR",
        re.compile(r"repo:[^/:\s]+/([A-Za-z0-9._-]+):", re.IGNORECASE),
        0.97,
        "Terraform GitHub Actions subject references the target repository",
    ),
)
_CLUSTER_RE = re.compile(
    r'resource\s+"aws_(?P<kind>ecs|eks)_cluster"\s+"[^"]+"\s*\{(?P<body>.*?)\n\}',
    re.IGNORECASE | re.DOTALL,
)
_MODULE_RE = re.compile(
    r'module\s+"(?P<module_name>[^"]+)"\s*\{(?P<body>.*?)\n\}',
    re.IGNORECASE | re.DOTALL,
)
_QUOTED_VALUE_RE = re.compile(r'\b(?P<key>[A-Za-z0-9_]+)\b\s*=\s*"(?P<value>[^"]+)"')


def discover_terraform_evidence(
    checkouts: Sequence[RepositoryCheckout],
    catalog: Sequence[CatalogEntry],
) -> list[RelationshipEvidenceFact]:
    """Extract repository and platform evidence from Terraform-like files."""

    evidence: list[RelationshipEvidenceFact] = []
    seen: set[tuple[str, str, str, str]] = set()
    for checkout in checkouts:
        for file_path in iter_checkout_files(checkout):
            if not is_terraform_file(file_path):
                continue
            content = read_text(file_path)
            if content is None:
                continue
            for (
                evidence_kind,
                relationship_type,
                pattern,
                confidence,
                rationale,
            ) in _TERRAFORM_PATTERNS:
                for match in pattern.finditer(content):
                    append_evidence_for_candidate(
                        evidence=evidence,
                        seen=seen,
                        catalog=catalog,
                        source_repo_id=checkout.logical_repo_id,
                        candidate=(match.group(1) or "").strip(),
                        evidence_kind=evidence_kind,
                        relationship_type=relationship_type,
                        confidence=confidence,
                        rationale=rationale,
                        path=file_path,
                        extractor="terraform",
                    )
            evidence.extend(
                _discover_terraform_platform_evidence(
                    checkout=checkout,
                    catalog=catalog,
                    content=content,
                    file_path=file_path,
                    seen=seen,
                )
            )
    return evidence


def _discover_terraform_platform_evidence(
    *,
    checkout: RepositoryCheckout,
    catalog: Sequence[CatalogEntry],
    content: str,
    file_path: Path,
    seen: set[tuple[str, str, str, str]],
) -> list[RelationshipEvidenceFact]:
    """Extract ECS platform provisioning and runtime evidence from one file."""

    evidence: list[RelationshipEvidenceFact] = []
    kind = infer_terraform_platform_kind(content)
    if kind is None:
        return evidence
    environment = _first_quoted_value(content, "cloudmap_namespace")
    clusters = {
        cluster_name
        for cluster_name in (
            _cluster_name_from_body(match.group("body"))
            for match in _CLUSTER_RE.finditer(content)
            if match.group("kind").lower() == kind
        )
        if cluster_name
    }
    for cluster_name in sorted(clusters):
        platform_id = _terraform_platform_id(
            kind=kind,
            name=cluster_name,
            environment=environment,
        )
        if platform_id is None:
            continue
        append_relationship_evidence(
            evidence=evidence,
            seen=seen,
            source_repo_id=checkout.logical_repo_id,
            target_repo_id=None,
            source_entity_id=checkout.logical_repo_id,
            target_entity_id=platform_id,
            evidence_kind=(
                "TERRAFORM_ECS_CLUSTER"
                if kind == "ecs"
                else "TERRAFORM_EKS_CLUSTER"
            ),
            relationship_type="PROVISIONS_PLATFORM",
            confidence=0.99,
            rationale="Terraform provisions the cluster declared in this file",
            path=file_path,
            extractor="terraform",
            extra_details={
                "cluster_name": cluster_name,
                "environment": environment,
                "provider": "aws",
                "kind": kind,
            },
        )

    for match in _MODULE_RE.finditer(content):
        body = match.group("body")
        source = _first_quoted_value(body, "source") or ""
        if "ecs-application/aws" not in source.lower():
            continue
        cluster_name = _first_quoted_value(body, "cluster_name")
        app_repo = _first_quoted_value(body, "app_repo")
        environment_hint = _first_quoted_value(body, "cloudmap_namespace") or environment
        if not cluster_name or not app_repo:
            continue
        platform_id = _terraform_platform_id(
            kind=kind,
            name=cluster_name,
            environment=environment_hint,
        )
        if platform_id is None:
            continue
        for entry in catalog:
            if app_repo.lower() not in entry.aliases:
                continue
            append_relationship_evidence(
                evidence=evidence,
                seen=seen,
                source_repo_id=entry.repo_id,
                target_repo_id=None,
                source_entity_id=entry.repo_id,
                target_entity_id=platform_id,
                evidence_kind=(
                    "TERRAFORM_ECS_SERVICE"
                    if kind == "ecs"
                    else "TERRAFORM_EKS_SERVICE"
                ),
                relationship_type="RUNS_ON",
                confidence=0.97,
                rationale="Terraform service configuration binds the app to the cluster",
                path=file_path,
                extractor="terraform",
                extra_details={
                    "cluster_name": cluster_name,
                    "app_repo": app_repo,
                    "environment": environment_hint,
                    "provider": "aws",
                    "kind": kind,
                },
            )
    return evidence


def _cluster_name_from_body(body: str) -> str | None:
    """Extract a stable ECS cluster name from one resource body."""

    return extract_terraform_platform_name(body)


def _first_quoted_value(content: str, key: str) -> str | None:
    """Extract one quoted Terraform assignment value by key."""

    for match in _QUOTED_VALUE_RE.finditer(content):
        if match.group("key").lower() != key.lower():
            continue
        value = match.group("value").strip()
        if value:
            return value
    return None


def _terraform_platform_id(
    *,
    kind: str,
    name: str,
    environment: str | None,
) -> str | None:
    """Build a canonical platform id from Terraform cluster metadata."""

    return canonical_platform_id(
        kind=kind,
        provider="aws",
        name=name,
        environment=environment,
        region=None,
        locator=f"cluster/{name}",
    )


__all__ = ["discover_terraform_evidence"]
