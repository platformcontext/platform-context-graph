"""ArgoCD, Helm, and Kustomize raw file evidence extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..observability import get_observability
from ..tools.graph_builder_platforms import infer_gitops_platform_id
from ..utils.debug_log import emit_log_call, info_logger
from .file_evidence_support import (
    CatalogEntry,
    append_evidence_for_candidate,
    append_relationship_evidence,
    build_catalog,
    infer_environment_from_path,
    iter_argocd_deploy_repo_urls,
    iter_argocd_deployed_repo_identifiers,
    iter_argocd_destination_cluster_names,
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
        argocd = _discover_argocd_evidence(checkouts, resolved_catalog)
        evidence.extend(helm)
        evidence.extend(kustomize)
        evidence.extend(argocd)
        if gitops_span is not None:
            gitops_span.set_attribute("pcg.relationships.helm_evidence_count", len(helm))
            gitops_span.set_attribute(
                "pcg.relationships.kustomize_evidence_count",
                len(kustomize),
            )
            gitops_span.set_attribute(
                "pcg.relationships.argocd_evidence_count",
                len(argocd),
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
            for file_path in iter_checkout_files(checkout):
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


def _discover_argocd_evidence(
    checkouts: Sequence[RepositoryCheckout],
    catalog: Sequence[CatalogEntry],
) -> list[RelationshipEvidenceFact]:
    """Extract config discovery, deploy-source, and runtime evidence from ArgoCD."""

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
        runtime_count = 0
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
                            rationale=(
                                "ArgoCD ApplicationSet discovers config in the target repository"
                            ),
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
                                if not source_matches:
                                    source_matches = [(entry, "config-repo-fallback")]
                                for deploy_repo_url in iter_argocd_deploy_repo_urls(
                                    config_path
                                ):
                                    target_matches = match_catalog(
                                        deploy_repo_url,
                                        catalog,
                                    )
                                    for source_entry, source_alias in source_matches:
                                        for target_entry, target_alias in target_matches:
                                            if source_entry.repo_id == entry.repo_id:
                                                continue
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
                                                    "or overlays from the config repository"
                                                ),
                                                path=file_path,
                                                extractor="argocd",
                                                matched_value=deploy_repo_url,
                                                matched_alias=target_alias,
                                                extra_details={
                                                    "control_plane_repo_id": checkout.logical_repo_id,
                                                    "config_repo_id": entry.repo_id,
                                                    "config_path": str(
                                                        _config_relative_path(
                                                            config_path, target_root
                                                        )
                                                    ),
                                                    "deployed_repo_id": source_entry.repo_id,
                                                    "deployed_repo_match": source_alias,
                                                    "repo_url": repo_url,
                                                    "discovery_path": discovery_path,
                                                    "deploy_repo_url": deploy_repo_url,
                                                },
                                            )
                                            deploy_source_count += len(evidence) - before_deploy
                                for cluster_name in iter_argocd_destination_cluster_names(
                                    config_path
                                ):
                                    environment = infer_environment_from_path(
                                        _config_relative_path(config_path, target_root)
                                    )
                                    platform_id = infer_gitops_platform_id(
                                        repo_name=checkout.repo_name,
                                        repo_slug=checkout.repo_slug,
                                        content=content,
                                        platform_name=cluster_name,
                                        environment=environment,
                                        locator=f"cluster/{cluster_name}",
                                    )
                                    if platform_id is None:
                                        continue
                                    for source_entry, source_alias in source_matches:
                                        before_runtime = len(evidence)
                                        append_relationship_evidence(
                                            evidence=evidence,
                                            seen=seen,
                                            source_repo_id=source_entry.repo_id,
                                            target_repo_id=None,
                                            source_entity_id=source_entry.repo_id,
                                            target_entity_id=platform_id,
                                            evidence_kind="ARGOCD_DESTINATION_PLATFORM",
                                            relationship_type="RUNS_ON",
                                            confidence=0.98,
                                            rationale=(
                                                "ArgoCD ApplicationSet targets the runtime platform"
                                            ),
                                            path=file_path,
                                            extractor="argocd",
                                            extra_details={
                                                "control_plane_repo_id": checkout.logical_repo_id,
                                                "config_repo_id": entry.repo_id,
                                                "config_path": str(
                                                    _config_relative_path(
                                                        config_path, target_root
                                                    )
                                                ),
                                                "deployed_repo_id": source_entry.repo_id,
                                                "deployed_repo_match": source_alias,
                                                "repo_url": repo_url,
                                                "discovery_path": discovery_path,
                                                "cluster_name": cluster_name,
                                                "environment": environment,
                                            },
                                        )
                                        runtime_count += len(evidence) - before_runtime
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
            argocd_span.set_attribute(
                "pcg.relationships.runtime_evidence_count",
                runtime_count,
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


def _config_relative_path(config_path: Path, target_root: Path) -> Path:
    """Return the repo-relative path when possible."""

    try:
        return config_path.relative_to(target_root)
    except ValueError:
        return config_path


__all__ = ["discover_gitops_evidence"]
