"""Terraform and Terragrunt relationship evidence extraction."""

from __future__ import annotations

import re
from typing import Sequence

from .evidence_terraform_support import (
    checkout_cluster_references,
    checkout_local_string_values,
    discover_terraform_platform_evidence,
)
from .file_evidence_support import (
    CatalogEntry,
    append_evidence_for_candidate,
    checkout_path_exists,
    is_terraform_file,
    iter_checkout_files,
    iter_terraform_files_from_content_store,
    read_text,
)
from .models import RelationshipEvidenceFact, RepositoryCheckout
from .terraform_evidence import discover_terraform_resource_evidence

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
def discover_terraform_evidence(
    checkouts: Sequence[RepositoryCheckout],
    catalog: Sequence[CatalogEntry],
) -> list[RelationshipEvidenceFact]:
    """Extract repository and platform evidence from Terraform-like files."""

    evidence: list[RelationshipEvidenceFact] = []
    seen: set[tuple[str, str, str, str]] = set()
    for checkout in checkouts:
        # Content store is the authoritative source — try it first.
        terraform_files = iter_terraform_files_from_content_store(checkout)
        if not terraform_files and checkout_path_exists(checkout):
            terraform_files = []
            for file_path in iter_checkout_files(checkout):
                if not is_terraform_file(file_path):
                    continue
                content = read_text(file_path)
                if content is None:
                    continue
                terraform_files.append((file_path, content))
        local_values = checkout_local_string_values(terraform_files)
        cluster_references = checkout_cluster_references(
            terraform_files,
            local_values=local_values,
        )
        for file_path, content in terraform_files:
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
                discover_terraform_platform_evidence(
                    checkout=checkout,
                    catalog=catalog,
                    content=content,
                    file_path=file_path,
                    local_values=local_values,
                    cluster_references=cluster_references,
                    seen=seen,
                )
            )
            # Registry-based resource extractors (per-provider modules).
            evidence.extend(
                discover_terraform_resource_evidence(
                    checkout=checkout,
                    catalog=catalog,
                    content=content,
                    file_path=file_path,
                    local_values=local_values,
                    seen=seen,
                )
            )
    return evidence

__all__ = ["discover_terraform_evidence"]
