"""Raw file-based repository dependency evidence extraction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from ..observability import get_observability
from ..utils.debug_log import emit_log_call, info_logger
from .file_evidence_support import (
    CatalogEntry,
    append_evidence_for_candidate,
    build_catalog,
    is_terraform_file,
    iter_argocd_deployed_repo_identifiers,
    iter_argocd_deploy_repo_urls,
    iter_argocd_discovered_config_files,
    iter_argocd_discovery_targets,
    iter_checkout_files,
    iter_kustomize_helm_strings,
    iter_kustomize_image_strings,
    iter_kustomize_resource_strings,
    iter_yaml_strings,
    load_yaml_documents,
    load_yaml_documents_from_text,
    match_catalog,
    read_text,
)
from .models import RelationshipEvidenceFact, RepositoryCheckout

_HELM_CHART_FILENAMES = {"chart.yaml", "chart.yml"}
_HELM_VALUES_PREFIX = "values"
_KUSTOMIZATION_FILENAMES = {"kustomization.yaml", "kustomization.yml"}
_YAML_SUFFIXES = (".yaml", ".yml")
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


def discover_checkout_file_evidence(
    checkouts: Sequence[RepositoryCheckout],
) -> list[RelationshipEvidenceFact]:
    """Extract repo dependency evidence directly from Terraform, Helm, and Kustomize."""

    catalog = build_catalog(checkouts)
    if not catalog:
        return []

    observability = get_observability()
    with observability.start_span(
        "pcg.relationships.discover_evidence.file",
        component=observability.component,
        attributes={"pcg.relationships.checkout_count": len(checkouts)},
    ) as root_span:
        terraform = _discover_terraform_evidence(checkouts, catalog)
        helm = _discover_helm_evidence(checkouts, catalog)
        kustomize = _discover_kustomize_evidence(checkouts, catalog)
        argocd = _discover_argocd_applicationset_evidence(checkouts, catalog)
        evidence = terraform + helm + kustomize + argocd
        if root_span is not None:
            root_span.set_attribute(
                "pcg.relationships.terraform_evidence_count", len(terraform)
            )
            root_span.set_attribute("pcg.relationships.helm_evidence_count", len(helm))
            root_span.set_attribute(
                "pcg.relationships.kustomize_evidence_count",
                len(kustomize),
            )
            root_span.set_attribute(
                "pcg.relationships.argocd_evidence_count",
                len(argocd),
            )
            root_span.set_attribute(
                "pcg.relationships.file_evidence_count", len(evidence)
            )
        emit_log_call(
            info_logger,
            "Discovered raw file-based repository dependency evidence",
            event_name="relationships.discover_file_evidence.completed",
            extra_keys={
                "terraform_evidence_count": len(terraform),
                "helm_evidence_count": len(helm),
                "kustomize_evidence_count": len(kustomize),
                "argocd_evidence_count": len(argocd),
                "evidence_count": len(evidence),
            },
        )
        return evidence


def _discover_terraform_evidence(
    checkouts: Sequence[RepositoryCheckout],
    catalog: Sequence[CatalogEntry],
) -> list[RelationshipEvidenceFact]:
    """Extract repository dependency evidence from Terraform and Terragrunt files."""

    observability = get_observability()
    evidence: list[RelationshipEvidenceFact] = []
    seen: set[tuple[str, str, str, str]] = set()
    with observability.start_span(
        "pcg.relationships.discover_evidence.terraform",
        component=observability.component,
        attributes={"pcg.relationships.checkout_count": len(checkouts)},
    ) as terraform_span:
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
        if terraform_span is not None:
            terraform_span.set_attribute("pcg.relationships.evidence_count", len(evidence))
    return evidence


def _discover_helm_evidence(
    checkouts: Sequence[RepositoryCheckout],
    catalog: Sequence[CatalogEntry],
) -> list[RelationshipEvidenceFact]:
    """Extract repository dependency evidence from Helm chart metadata and values."""

    observability = get_observability()
    evidence: list[RelationshipEvidenceFact] = []
    seen: set[tuple[str, str, str, str]] = set()
    with observability.start_span(
        "pcg.relationships.discover_evidence.helm",
        component=observability.component,
        attributes={"pcg.relationships.checkout_count": len(checkouts)},
    ) as helm_span:
        for checkout in checkouts:
            for file_path in iter_checkout_files(checkout):
                lower_name = file_path.name.lower()
                if lower_name not in _HELM_CHART_FILENAMES and not (
                    lower_name.startswith(_HELM_VALUES_PREFIX)
                    and lower_name.endswith((".yaml", ".yml"))
                ):
                    continue
                evidence_kind = (
                    "HELM_CHART_REFERENCE"
                    if lower_name in _HELM_CHART_FILENAMES
                    else "HELM_VALUES_REFERENCE"
                )
                confidence = 0.9 if evidence_kind == "HELM_CHART_REFERENCE" else 0.84
                rationale = (
                    "Helm chart metadata references the target repository"
                    if evidence_kind == "HELM_CHART_REFERENCE"
                    else "Helm values reference the target repository"
                )
                for document in load_yaml_documents(file_path):
                    for value in iter_yaml_strings(document):
                        _append_repo_deploy_source_evidence(
                            evidence=evidence,
                            seen=seen,
                            catalog=catalog,
                            source_candidate=value,
                            target_repo_id=checkout.logical_repo_id,
                            evidence_kind=evidence_kind,
                            confidence=confidence,
                            rationale=rationale,
                            path=file_path,
                            extractor="helm",
                        )
        if helm_span is not None:
            helm_span.set_attribute("pcg.relationships.evidence_count", len(evidence))
    return evidence


def _discover_kustomize_evidence(
    checkouts: Sequence[RepositoryCheckout],
    catalog: Sequence[CatalogEntry],
) -> list[RelationshipEvidenceFact]:
    """Extract repository dependency evidence from Kustomize overlays."""

    observability = get_observability()
    evidence: list[RelationshipEvidenceFact] = []
    seen: set[tuple[str, str, str, str]] = set()
    with observability.start_span(
        "pcg.relationships.discover_evidence.kustomize",
        component=observability.component,
        attributes={"pcg.relationships.checkout_count": len(checkouts)},
    ) as kustomize_span:
        for checkout in checkouts:
            for file_path in iter_checkout_files(checkout):
                if file_path.name.lower() not in _KUSTOMIZATION_FILENAMES:
                    continue
                for document in load_yaml_documents(file_path):
                    for evidence_kind, rationale, values in (
                        (
                            "KUSTOMIZE_RESOURCE_REFERENCE",
                            "Kustomize resources source deployment config from the target repository",
                            iter_kustomize_resource_strings(document),
                        ),
                        (
                            "KUSTOMIZE_HELM_CHART_REFERENCE",
                            "Kustomize Helm configuration deploys from the target repository",
                            iter_kustomize_helm_strings(document),
                        ),
                        (
                            "KUSTOMIZE_IMAGE_REFERENCE",
                            "Kustomize image configuration deploys artifacts from the target repository",
                            iter_kustomize_image_strings(document),
                        ),
                    ):
                        for value in values:
                            _append_repo_deploy_source_evidence(
                                evidence=evidence,
                                seen=seen,
                                catalog=catalog,
                                source_candidate=value,
                                target_repo_id=checkout.logical_repo_id,
                                evidence_kind=evidence_kind,
                                confidence=0.9
                                if evidence_kind == "KUSTOMIZE_RESOURCE_REFERENCE"
                                else 0.89
                                if evidence_kind == "KUSTOMIZE_HELM_CHART_REFERENCE"
                                else 0.86,
                                rationale=rationale,
                                path=file_path,
                                extractor="kustomize",
                            )
        if kustomize_span is not None:
            kustomize_span.set_attribute("pcg.relationships.evidence_count", len(evidence))
    return evidence


def _discover_argocd_applicationset_evidence(
    checkouts: Sequence[RepositoryCheckout],
    catalog: Sequence[CatalogEntry],
) -> list[RelationshipEvidenceFact]:
    """Extract repo discovery evidence from ArgoCD ApplicationSet generators."""

    observability = get_observability()
    evidence: list[RelationshipEvidenceFact] = []
    seen: set[tuple[str, str, str, str]] = set()
    checkout_roots = {
        checkout.logical_repo_id: Path(checkout.checkout_path)
        for checkout in checkouts
        if checkout.checkout_path
    }
    with observability.start_span(
        "pcg.relationships.discover_evidence.argocd",
        component=observability.component,
        attributes={"pcg.relationships.checkout_count": len(checkouts)},
    ) as argocd_span:
        discovery_count = 0
        deploy_source_count = 0
        for checkout in checkouts:
            for file_path in iter_checkout_files(checkout):
                if file_path.suffix.lower() not in _YAML_SUFFIXES:
                    continue
                content = read_text(file_path)
                if content is None or "applicationset" not in content.lower():
                    continue
                for document in load_yaml_documents_from_text(content):
                    for repo_url, discovery_path in iter_argocd_discovery_targets(document):
                        before_discovery = len(evidence)
                        append_evidence_for_candidate(
                            evidence=evidence,
                            seen=seen,
                            catalog=catalog,
                            source_repo_id=checkout.logical_repo_id,
                            candidate=repo_url,
                            evidence_kind="ARGOCD_APPLICATIONSET_DISCOVERY",
                            relationship_type="DISCOVERS_CONFIG_IN",
                            confidence=0.99,
                            rationale="ArgoCD ApplicationSet discovers config in the target repository",
                            path=file_path,
                            extractor="argocd",
                            extra_details={
                                "repo_url": repo_url,
                                "discovery_path": discovery_path,
                            },
                        )
                        discovery_count += len(evidence) - before_discovery
                        for entry, _matched_alias in match_catalog(repo_url, catalog):
                            if entry.repo_id == checkout.logical_repo_id:
                                continue
                            target_root = checkout_roots.get(entry.repo_id)
                            if target_root is None:
                                continue
                            for config_path in iter_argocd_discovered_config_files(
                                target_root,
                                discovery_path,
                            ):
                                source_matches = []
                                for candidate in iter_argocd_deployed_repo_identifiers(
                                    config_path,
                                    target_root,
                                ):
                                    source_matches.extend(match_catalog(candidate, catalog))
                                for deploy_repo_url in iter_argocd_deploy_repo_urls(
                                    config_path
                                ):
                                    target_matches = match_catalog(
                                        deploy_repo_url,
                                        catalog,
                                    )
                                    for source_entry, source_alias in source_matches:
                                        for target_entry, target_alias in target_matches:
                                            before_deploy = len(evidence)
                                            _append_matched_evidence(
                                                evidence=evidence,
                                                seen=seen,
                                                source_repo_id=source_entry.repo_id,
                                                target_repo_id=target_entry.repo_id,
                                                evidence_kind="ARGOCD_APPLICATIONSET_DEPLOY_SOURCE",
                                                relationship_type="DEPLOYS_FROM",
                                                confidence=0.99,
                                                rationale=(
                                                    "The deployed repository sources manifests "
                                                    "or overlays from the target repository"
                                                ),
                                                path=file_path,
                                                extractor="argocd",
                                                matched_value=deploy_repo_url,
                                                matched_alias=target_alias,
                                                extra_details={
                                                    "control_plane_repo_id": checkout.logical_repo_id,
                                                    "config_repo_id": entry.repo_id,
                                                    "config_path": str(
                                                        config_path.relative_to(target_root)
                                                    ),
                                                    "deployed_repo_id": source_entry.repo_id,
                                                    "deployed_repo_match": source_alias,
                                                    "repo_url": repo_url,
                                                    "discovery_path": discovery_path,
                                                    "deploy_repo_url": deploy_repo_url,
                                                },
                                            )
                                            deploy_source_count += len(evidence) - before_deploy
        if argocd_span is not None:
            argocd_span.set_attribute("pcg.relationships.evidence_count", len(evidence))
            argocd_span.set_attribute(
                "pcg.relationships.discovery_evidence_count",
                discovery_count,
            )
            argocd_span.set_attribute(
                "pcg.relationships.deploy_source_evidence_count",
                deploy_source_count,
            )
    return evidence


def _append_repo_deploy_source_evidence(
    *,
    evidence: list[RelationshipEvidenceFact],
    seen: set[tuple[str, str, str, str]],
    catalog: Sequence[CatalogEntry],
    source_candidate: str,
    target_repo_id: str,
    evidence_kind: str,
    confidence: float,
    rationale: str,
    path: Path,
    extractor: str,
) -> None:
    """Append DEPLOYS_FROM evidence from a matched repo toward the current checkout."""

    for entry, matched_alias in match_catalog(source_candidate, catalog):
        _append_matched_evidence(
            evidence=evidence,
            seen=seen,
            source_repo_id=entry.repo_id,
            target_repo_id=target_repo_id,
            evidence_kind=evidence_kind,
            relationship_type="DEPLOYS_FROM",
            confidence=confidence,
            rationale=rationale,
            path=path,
            extractor=extractor,
            matched_value=source_candidate,
            matched_alias=matched_alias,
        )


def _append_matched_evidence(
    *,
    evidence: list[RelationshipEvidenceFact],
    seen: set[tuple[str, str, str, str]],
    source_repo_id: str,
    target_repo_id: str,
    evidence_kind: str,
    relationship_type: str,
    confidence: float,
    rationale: str,
    path: Path,
    extractor: str,
    matched_value: str,
    matched_alias: str,
    extra_details: dict[str, object] | None = None,
) -> None:
    """Append one evidence fact for a concrete repo pair."""

    if source_repo_id == target_repo_id:
        return
    key = (evidence_kind, source_repo_id, target_repo_id, str(path))
    if key in seen:
        return
    seen.add(key)
    evidence.append(
        RelationshipEvidenceFact(
            evidence_kind=evidence_kind,
            relationship_type=relationship_type,
            source_repo_id=source_repo_id,
            target_repo_id=target_repo_id,
            confidence=confidence,
            rationale=rationale,
            details={
                "path": str(path),
                "matched_alias": matched_alias,
                "matched_value": matched_value,
                "extractor": extractor,
                **(extra_details or {}),
            },
        )
    )


__all__ = ["discover_checkout_file_evidence"]
