"""ArgoCD, Helm, and Kustomize raw file evidence extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..observability import get_observability
from ..utils.debug_log import emit_log_call, info_logger
from .evidence_argocd import discover_argocd_evidence
from .file_evidence_support import (
    CatalogEntry,
    build_catalog,
    checkout_path_exists,
    iter_checkout_files,
    iter_kustomize_helm_strings,
    iter_kustomize_image_strings,
    iter_kustomize_resource_strings,
    iter_yaml_files_from_content_store,
    iter_yaml_strings,
    load_yaml_documents,
    load_yaml_documents_from_text,
    match_catalog,
)
from .models import RelationshipEvidenceFact, RepositoryCheckout

_HELM_CHART_FILENAMES = {"chart.yaml", "chart.yml"}
_HELM_VALUES_PREFIX = "values"
_KUSTOMIZATION_FILENAMES = {"kustomization.yaml", "kustomization.yml"}
_YAML_SUFFIXES = (".yaml", ".yml")


def discover_gitops_evidence(
    checkouts: Sequence[RepositoryCheckout],
    catalog: Sequence[CatalogEntry] | None = None,
) -> list[RelationshipEvidenceFact]:
    """Extract repository, deployment, and runtime evidence from GitOps files."""

    resolved_catalog = catalog if catalog is not None else build_catalog(checkouts)
    if not resolved_catalog:
        return []

    observability = get_observability()
    evidence: list[RelationshipEvidenceFact] = []
    with observability.start_span(
        "pcg.relationships.discover_evidence.gitops",
        component=observability.component,
        attributes={"pcg.relationships.checkout_count": len(checkouts)},
    ) as gitops_span:
        helm = _discover_helm_evidence(checkouts, resolved_catalog)
        kustomize = _discover_kustomize_evidence(checkouts, resolved_catalog)
        argocd, argocd_counts = discover_argocd_evidence(
            checkouts=checkouts,
            catalog=resolved_catalog,
        )
        evidence.extend(helm)
        evidence.extend(kustomize)
        evidence.extend(argocd)
        if gitops_span is not None:
            gitops_span.set_attribute(
                "pcg.relationships.helm_evidence_count", len(helm)
            )
            gitops_span.set_attribute(
                "pcg.relationships.kustomize_evidence_count",
                len(kustomize),
            )
            gitops_span.set_attribute(
                "pcg.relationships.argocd_evidence_count",
                len(argocd),
            )
            gitops_span.set_attribute(
                "pcg.relationships.discovery_evidence_count",
                argocd_counts["discovery"],
            )
            gitops_span.set_attribute(
                "pcg.relationships.deploy_source_evidence_count",
                argocd_counts["deploy_source"],
            )
            gitops_span.set_attribute(
                "pcg.relationships.runtime_evidence_count",
                argocd_counts["runtime"],
            )
            gitops_span.set_attribute("pcg.relationships.evidence_count", len(evidence))
    emit_log_call(
        info_logger,
        "Discovered GitOps dependency and platform evidence",
        event_name="relationships.discover_gitops_evidence.completed",
        extra_keys={
            "helm_evidence_count": len(helm),
            "kustomize_evidence_count": len(kustomize),
            "argocd_evidence_count": len(argocd),
            "argocd_discovery_evidence_count": argocd_counts["discovery"],
            "argocd_deploy_source_evidence_count": argocd_counts["deploy_source"],
            "argocd_runtime_evidence_count": argocd_counts["runtime"],
            "evidence_count": len(evidence),
        },
    )
    return evidence


def _discover_helm_evidence(
    checkouts: Sequence[RepositoryCheckout],
    catalog: Sequence[CatalogEntry],
) -> list[RelationshipEvidenceFact]:
    """Extract DEPLOYS_FROM evidence from Helm chart metadata and values."""

    observability = get_observability()
    evidence: list[RelationshipEvidenceFact] = []
    seen: set[tuple[str, str, str, str]] = set()
    with observability.start_span(
        "pcg.relationships.discover_evidence.helm",
        component=observability.component,
        attributes={"pcg.relationships.checkout_count": len(checkouts)},
    ) as helm_span:
        for checkout in checkouts:
            yaml_files = iter_yaml_files_from_content_store(checkout)
            if not yaml_files and checkout_path_exists(checkout):
                yaml_files = [
                    (file_path, None)
                    for file_path in iter_checkout_files(checkout)
                    if file_path.suffix.lower() in _YAML_SUFFIXES
                ]
            for file_path, content in yaml_files:
                lower_name = file_path.name.lower()
                if lower_name not in _HELM_CHART_FILENAMES and not (
                    lower_name.startswith(_HELM_VALUES_PREFIX)
                    and lower_name.endswith(_YAML_SUFFIXES)
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
                documents = (
                    load_yaml_documents_from_text(content)
                    if content is not None
                    else load_yaml_documents(file_path)
                )
                for document in documents:
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
    """Extract DEPLOYS_FROM evidence from Kustomize overlays."""

    observability = get_observability()
    evidence: list[RelationshipEvidenceFact] = []
    seen: set[tuple[str, str, str, str]] = set()
    with observability.start_span(
        "pcg.relationships.discover_evidence.kustomize",
        component=observability.component,
        attributes={"pcg.relationships.checkout_count": len(checkouts)},
    ) as kustomize_span:
        for checkout in checkouts:
            yaml_files = iter_yaml_files_from_content_store(checkout)
            if not yaml_files and checkout_path_exists(checkout):
                yaml_files = [
                    (file_path, None)
                    for file_path in iter_checkout_files(checkout)
                    if file_path.suffix.lower() in _YAML_SUFFIXES
                ]
            for file_path, content in yaml_files:
                if file_path.name.lower() not in _KUSTOMIZATION_FILENAMES:
                    continue
                documents = (
                    load_yaml_documents_from_text(content)
                    if content is not None
                    else load_yaml_documents(file_path)
                )
                for document in documents:
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
                                confidence=(
                                    0.9
                                    if evidence_kind == "KUSTOMIZE_RESOURCE_REFERENCE"
                                    else (
                                        0.89
                                        if evidence_kind
                                        == "KUSTOMIZE_HELM_CHART_REFERENCE"
                                        else 0.86
                                    )
                                ),
                                rationale=rationale,
                                path=file_path,
                                extractor="kustomize",
                            )
        if kustomize_span is not None:
            kustomize_span.set_attribute(
                "pcg.relationships.evidence_count", len(evidence)
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
) -> None:
    """Append one evidence fact for a concrete repository pair."""

    key = (evidence_kind, source_repo_id, target_repo_id, str(path))
    if key in seen or source_repo_id == target_repo_id:
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
            },
        )
    )


__all__ = ["discover_gitops_evidence"]
