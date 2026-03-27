"""ArgoCD raw file evidence extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..observability import get_observability
from ..tools.graph_builder_platforms import infer_gitops_platform_id
from .entities import WorkloadSubjectEntity
from .file_evidence_argocd_support import (
    extract_argocd_subject_name,
    infer_environment_from_path,
    iter_argocd_applicationset_source_repo_urls,
    iter_argocd_deployed_repo_identifiers,
    iter_argocd_deploy_repo_urls,
    iter_argocd_destination_cluster_names,
    iter_argocd_discovered_config_files,
    iter_argocd_discovery_targets,
)
from .file_evidence_support import (
    CatalogEntry,
    append_evidence_for_candidate,
    append_relationship_evidence,
    iter_checkout_files,
    load_yaml_documents_from_text,
    match_catalog,
    read_text,
)
from .models import RelationshipEvidenceFact, RepositoryCheckout

_YAML_SUFFIXES = (".yaml", ".yml")


def discover_argocd_evidence(
    checkouts: Sequence[RepositoryCheckout],
    catalog: Sequence[CatalogEntry],
) -> tuple[list[RelationshipEvidenceFact], dict[str, int]]:
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
                    for repo_url, discovery_path in iter_argocd_discovery_targets(
                        document
                    ):
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
                                config_relative_path = _config_relative_path(
                                    config_path, target_root
                                )
                                environment = infer_environment_from_path(
                                    config_relative_path
                                )
                                source_refs = _argocd_source_references(
                                    entry=entry,
                                    config_path=config_path,
                                    target_root=target_root,
                                    catalog=catalog,
                                    environment=environment,
                                )
                                deploy_repo_urls = list(
                                    dict.fromkeys(
                                        [
                                            *iter_argocd_deploy_repo_urls(config_path),
                                            *iter_argocd_applicationset_source_repo_urls(
                                                document
                                            ),
                                        ]
                                    )
                                )
                                for deploy_repo_url in deploy_repo_urls:
                                    target_matches = match_catalog(
                                        deploy_repo_url,
                                        catalog,
                                    )
                                    for (
                                        source_repo_id,
                                        source_entity_id,
                                        source_alias,
                                    ) in source_refs:
                                        for target_entry, target_alias in target_matches:
                                            if (
                                                source_entity_id.startswith(
                                                    "workload-subject:"
                                                )
                                                and target_entry.repo_id
                                                in {
                                                    entry.repo_id,
                                                    checkout.logical_repo_id,
                                                }
                                            ):
                                                continue
                                            if source_entity_id == target_entry.repo_id:
                                                continue
                                            before_deploy = len(evidence)
                                            _append_matched_evidence(
                                                evidence=evidence,
                                                seen=seen,
                                                source_repo_id=source_repo_id,
                                                target_repo_id=target_entry.repo_id,
                                                source_entity_id=source_entity_id,
                                                target_entity_id=target_entry.repo_id,
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
                                                    "config_path": str(config_relative_path),
                                                    "deployed_repo_id": source_repo_id,
                                                    "deployed_entity_id": source_entity_id,
                                                    "deployed_repo_match": source_alias,
                                                    "repo_url": repo_url,
                                                    "discovery_path": discovery_path,
                                                    "deploy_repo_url": deploy_repo_url,
                                                },
                                            )
                                            deploy_source_count += (
                                                len(evidence) - before_deploy
                                            )
                                for cluster_name in iter_argocd_destination_cluster_names(
                                    config_path
                                ):
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
                                    for (
                                        source_repo_id,
                                        source_entity_id,
                                        source_alias,
                                    ) in source_refs:
                                        before_runtime = len(evidence)
                                        append_relationship_evidence(
                                            evidence=evidence,
                                            seen=seen,
                                            source_repo_id=source_repo_id,
                                            target_repo_id=None,
                                            source_entity_id=source_entity_id,
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
                                                "config_path": str(config_relative_path),
                                                "deployed_repo_id": source_repo_id,
                                                "deployed_entity_id": source_entity_id,
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
    return (
        evidence,
        {
            "discovery": discovery_count,
            "deploy_source": deploy_source_count,
            "runtime": runtime_count,
        },
    )


def _append_matched_evidence(
    *,
    evidence: list[RelationshipEvidenceFact],
    seen: set[tuple[str, str, str, str]],
    source_repo_id: str,
    target_repo_id: str,
    source_entity_id: str | None = None,
    target_entity_id: str | None = None,
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
    """Append one evidence fact for a concrete repo or entity pair."""

    source_identity = source_entity_id or source_repo_id
    target_identity = target_entity_id or target_repo_id
    if source_identity == target_identity:
        return
    key = (evidence_kind, source_identity, target_identity, str(path))
    if key in seen:
        return
    seen.add(key)
    evidence.append(
        RelationshipEvidenceFact(
            evidence_kind=evidence_kind,
            relationship_type=relationship_type,
            source_repo_id=source_repo_id,
            target_repo_id=target_repo_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
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


def _argocd_source_references(
    *,
    entry: CatalogEntry,
    config_path: Path,
    target_root: Path,
    catalog: Sequence[CatalogEntry],
    environment: str | None,
) -> list[tuple[str, str, str]]:
    """Return deployable repo or workload-subject references for one config file."""

    references: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in iter_argocd_deployed_repo_identifiers(config_path, target_root):
        for matched_entry, matched_alias in match_catalog(candidate, catalog):
            key = (matched_entry.repo_id, matched_entry.repo_id)
            if key in seen:
                continue
            seen.add(key)
            references.append(
                (matched_entry.repo_id, matched_entry.repo_id, matched_alias)
            )
    if references:
        return references

    subject_name = extract_argocd_subject_name(config_path) or entry.repo_name
    subject = WorkloadSubjectEntity.from_parts(
        repository_id=entry.repo_id,
        subject_type="argocd-config",
        name=subject_name,
        environment=environment,
        path=str(_config_relative_path(config_path, target_root)),
    )
    return [(entry.repo_id, subject.entity_id, "workload-subject")]


def _config_relative_path(config_path: Path, target_root: Path) -> Path:
    """Return the repo-relative path when possible."""

    try:
        return config_path.relative_to(target_root)
    except ValueError:
        return config_path


__all__ = ["discover_argocd_evidence"]
