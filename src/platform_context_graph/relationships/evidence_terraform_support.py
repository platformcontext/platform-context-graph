"""Support helpers for Terraform evidence extraction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from ..tools.graph_builder_platforms import (
    extract_terraform_platform_name,
    infer_terraform_platform_kind,
)
from ..resolution.platform_families import (
    lookup_runtime_family,
    matches_service_module_source,
    terraform_platform_evidence_kind,
)
from .entities import canonical_platform_id
from .file_evidence_support import CatalogEntry, append_relationship_evidence
from .models import RelationshipEvidenceFact, RepositoryCheckout

CLUSTER_RE = re.compile(
    r'resource\s+"aws_(?P<kind>ecs|eks)_cluster"\s+"(?P<resource_name>[^"]+)"\s*\{(?P<body>.*?)\n\}',
    re.IGNORECASE | re.DOTALL,
)
PLATFORM_RESOURCE_RE = re.compile(
    r'resource\s+"(?P<resource_type>'
    r"aws_lambda_function"
    r"|cloudflare_workers_script"
    r"|google_container_cluster"
    r"|google_cloud_run_service"
    r"|google_cloud_run_v2_service"
    r"|azurerm_kubernetes_cluster"
    r"|azurerm_container_app"
    r')"\s+"(?P<resource_name>[^"]+)"\s*\{(?P<body>.*?)\n\}',
    re.IGNORECASE | re.DOTALL,
)
PLATFORM_RESOURCE_TYPE_TO_KIND: dict[str, str] = {
    "aws_lambda_function": "lambda",
    "cloudflare_workers_script": "cloudflare_workers",
    "google_container_cluster": "gke",
    "google_cloud_run_service": "cloud_run",
    "google_cloud_run_v2_service": "cloud_run",
    "azurerm_kubernetes_cluster": "aks",
    "azurerm_container_app": "container_apps",
}
SERVICE_NAME_KEYS: tuple[str, ...] = ("function_name", "name", "script_name")
MODULE_RE = re.compile(
    r'module\s+"(?P<module_name>[^"]+)"\s*\{(?P<body>.*?)\n\}',
    re.IGNORECASE | re.DOTALL,
)
LOCALS_RE = re.compile(r"locals\s*\{(?P<body>.*?)\n\}", re.IGNORECASE | re.DOTALL)
QUOTED_VALUE_RE = re.compile(r'\b(?P<key>[A-Za-z0-9_]+)\b\s*=\s*"(?P<value>[^"]+)"')
ASSIGNMENT_RE = re.compile(
    r"^\s*(?P<key>[A-Za-z0-9_]+)\s*=\s*(?P<value>[^#\n]+)",
    re.MULTILINE,
)


def discover_terraform_platform_evidence(
    *,
    checkout: RepositoryCheckout,
    catalog: Sequence[CatalogEntry],
    content: str,
    file_path: Path,
    local_values: dict[str, str],
    cluster_references: dict[str, str],
    seen: set[tuple[str, str, str, str]],
) -> list[RelationshipEvidenceFact]:
    """Extract platform provisioning and runtime evidence from one file."""
    evidence = discover_resource_platform_evidence(
        checkout=checkout,
        catalog=catalog,
        content=content,
        file_path=file_path,
        local_values=local_values,
        seen=seen,
    )
    kind = infer_terraform_platform_kind(content)
    if kind is None:
        return evidence
    family = lookup_runtime_family(kind)
    provider = family.provider if family is not None else "aws"
    environment = first_quoted_value(content, "cloudmap_namespace")
    clusters = {
        cluster_name
        for cluster_name in (
            cluster_name_from_body(match.group("body"), local_values=local_values)
            for match in CLUSTER_RE.finditer(content)
            if match.group("kind").lower() == kind
        )
        if cluster_name
    }
    for match in CLUSTER_RE.finditer(content):
        if match.group("kind").lower() != kind:
            continue
        cluster_name = cluster_name_from_body(
            match.group("body"),
            local_values=local_values,
        )
        if not cluster_name:
            continue
        clusters.add(cluster_name)
        cluster_references[
            f"aws_{kind}_cluster.{match.group('resource_name')}.name"
        ] = cluster_name
    for cluster_name in sorted(clusters):
        platform_id = terraform_platform_id(
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
            evidence_kind=terraform_platform_evidence_kind(kind, scope="cluster"),
            relationship_type="PROVISIONS_PLATFORM",
            confidence=0.99,
            rationale="Terraform provisions the cluster declared in this file",
            path=file_path,
            extractor="terraform",
            extra_details={
                "cluster_name": cluster_name,
                "environment": environment,
                "provider": provider,
                "kind": kind,
            },
        )

    for match in MODULE_RE.finditer(content):
        body = match.group("body")
        source = first_quoted_value(body, "source") or ""
        if not matches_service_module_source(source, kind=kind):
            continue
        cluster_name = resolve_assignment_value(
            body,
            key="cluster_name",
            local_values=local_values,
            references=cluster_references,
        )
        app_repo = first_non_empty(
            first_quoted_value(body, "app_repo"),
            first_quoted_value(body, "repo_name"),
            first_quoted_value(body, "name"),
        )
        environment_hint = first_quoted_value(body, "cloudmap_namespace") or environment
        if not cluster_name or not app_repo:
            continue
        platform_id = terraform_platform_id(
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
                evidence_kind=terraform_platform_evidence_kind(kind, scope="service"),
                relationship_type="RUNS_ON",
                confidence=0.97,
                rationale="Terraform service configuration binds the app to the cluster",
                path=file_path,
                extractor="terraform",
                extra_details={
                    "cluster_name": cluster_name,
                    "app_repo": app_repo,
                    "environment": environment_hint,
                    "provider": provider,
                    "kind": kind,
                },
            )
    return evidence


def discover_resource_platform_evidence(
    *,
    checkout: RepositoryCheckout,
    catalog: Sequence[CatalogEntry],
    content: str,
    file_path: Path,
    local_values: dict[str, str],
    seen: set[tuple[str, str, str, str]],
) -> list[RelationshipEvidenceFact]:
    """Extract platform evidence from non-cluster resources like Lambda and Workers."""
    evidence: list[RelationshipEvidenceFact] = []
    for match in PLATFORM_RESOURCE_RE.finditer(content):
        resource_type = match.group("resource_type").lower()
        kind = PLATFORM_RESOURCE_TYPE_TO_KIND.get(resource_type)
        if kind is None:
            continue
        body = match.group("body")
        family = lookup_runtime_family(kind)
        provider = family.provider if family is not None else None
        resource_name = _resource_name_from_body(
            body=body,
            resource_name=match.group("resource_name"),
            local_values=local_values,
        )
        platform_id = terraform_platform_id(
            kind=kind,
            name=resource_name,
            environment=None,
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
            evidence_kind=terraform_platform_evidence_kind(kind, scope="resource"),
            relationship_type="PROVISIONS_PLATFORM",
            confidence=0.95,
            rationale=f"Terraform {resource_type} resource provisions the runtime platform",
            path=file_path,
            extractor="terraform",
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "provider": provider,
                "kind": kind,
            },
        )

        app_repo = first_non_empty(
            first_quoted_value(body, "app_repo"),
            first_quoted_value(body, "repo_name"),
            first_quoted_value(body, "function_name"),
            first_quoted_value(body, "script_name"),
        )
        if not app_repo:
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
                evidence_kind=terraform_platform_evidence_kind(kind, scope="service"),
                relationship_type="RUNS_ON",
                confidence=0.92,
                rationale=f"Terraform {resource_type} binds the application to the runtime",
                path=file_path,
                extractor="terraform",
                extra_details={
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "app_repo": app_repo,
                    "provider": provider,
                    "kind": kind,
                },
            )
    return evidence


def cluster_name_from_body(
    body: str,
    *,
    local_values: dict[str, str],
) -> str | None:
    """Extract a stable cluster name from one resource body."""
    name = extract_terraform_platform_name(body)
    if name:
        return name
    return resolve_assignment_value(
        body,
        key="name",
        local_values=local_values,
        references={},
    )


def first_quoted_value(content: str, key: str) -> str | None:
    """Extract one quoted Terraform assignment value by key."""
    for match in QUOTED_VALUE_RE.finditer(content):
        if match.group("key").lower() != key.lower():
            continue
        value = match.group("value").strip()
        if value:
            return value
    return None


def first_non_empty(*values: str | None) -> str | None:
    """Return the first non-empty string from the provided values."""
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def checkout_local_string_values(
    terraform_files: Sequence[tuple[Path, str]],
) -> dict[str, str]:
    """Extract simple quoted local assignments across one checkout."""
    values: dict[str, str] = {}
    for _file_path, content in terraform_files:
        values.update(local_string_values(content))
    return values


def checkout_cluster_references(
    terraform_files: Sequence[tuple[Path, str]],
    *,
    local_values: dict[str, str],
) -> dict[str, str]:
    """Extract canonical cluster-name references across one checkout."""
    references: dict[str, str] = {}
    for _file_path, content in terraform_files:
        for match in CLUSTER_RE.finditer(content):
            cluster_name = cluster_name_from_body(
                match.group("body"),
                local_values=local_values,
            )
            if not cluster_name:
                continue
            references[
                f"aws_{match.group('kind').lower()}_cluster.{match.group('resource_name')}.name"
            ] = cluster_name
    return references


def resolve_assignment_value(
    content: str,
    *,
    key: str,
    local_values: dict[str, str],
    references: dict[str, str],
) -> str | None:
    """Resolve one Terraform assignment value from quoted, local, or reference forms."""
    for match in ASSIGNMENT_RE.finditer(content):
        if match.group("key").strip().lower() != key.lower():
            continue
        resolved = resolve_expression(
            match.group("value"),
            local_values=local_values,
            references=references,
        )
        if resolved:
            return resolved
    return None


def resolve_expression(
    expression: str,
    *,
    local_values: dict[str, str],
    references: dict[str, str],
) -> str | None:
    """Resolve a small Terraform expression into a stable string when safe."""
    cleaned = expression.strip().rstrip(",")
    quoted = parse_quoted_literal(cleaned)
    if quoted:
        return quoted
    if cleaned.startswith("local."):
        return local_values.get(cleaned.split(".", 1)[1].strip())
    if cleaned in references:
        return references[cleaned]
    return None


def local_string_values(content: str) -> dict[str, str]:
    """Extract simple quoted local assignments for Terraform expression resolution."""
    values: dict[str, str] = {}
    for block in LOCALS_RE.finditer(content):
        for match in ASSIGNMENT_RE.finditer(block.group("body")):
            value = parse_quoted_literal(match.group("value"))
            if value is None:
                continue
            values[match.group("key").strip()] = value
    return values


def parse_quoted_literal(value: str) -> str | None:
    """Return the contents of one quoted string literal when present."""
    candidate = value.strip().rstrip(",")
    if len(candidate) >= 2 and candidate[0] == candidate[-1] == '"':
        return candidate[1:-1].strip() or None
    return None


def terraform_platform_id(
    *,
    kind: str,
    name: str,
    environment: str | None,
) -> str | None:
    """Build a canonical platform id from Terraform cluster metadata."""
    family = lookup_runtime_family(kind)
    return canonical_platform_id(
        kind=kind,
        provider=family.provider if family is not None else "aws",
        name=name,
        environment=environment,
        region=None,
        locator=f"cluster/{name}",
    )


def _resource_name_from_body(
    *,
    body: str,
    resource_name: str,
    local_values: dict[str, str],
) -> str:
    """Resolve a platform resource name from explicit literals or local refs."""

    for key in SERVICE_NAME_KEYS:
        resolved = first_quoted_value(body, key)
        if resolved:
            return resolved
    for key in SERVICE_NAME_KEYS:
        resolved = resolve_assignment_value(
            body,
            key=key,
            local_values=local_values,
            references={},
        )
        if resolved:
            return resolved
    return resource_name
