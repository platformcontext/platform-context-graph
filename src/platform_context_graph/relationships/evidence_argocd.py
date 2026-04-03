"""ArgoCD raw file evidence extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..observability import get_observability
from ..resolution.platforms import infer_gitops_platform_id
from .evidence_argocd_support import (
    append_matched_evidence,
    argocd_source_references_content_aware,
    config_relative_path,
    iter_deploy_urls_from_document,
    iter_destination_clusters_content_aware,
)
from .file_evidence_argocd_support import (
    infer_environment_from_path,
    iter_argocd_applicationset_source_repo_urls,
    iter_argocd_deploy_repo_urls,
    iter_argocd_discovered_config_files,
    iter_argocd_discovered_config_files_from_content_store,
    iter_argocd_discovery_targets,
)
from .file_evidence_support import (
    CatalogEntry,
    append_evidence_for_candidate,
    append_relationship_evidence,
    checkout_path_exists,
    iter_checkout_files,
    iter_yaml_files_from_content_store,
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
            yaml_files = iter_yaml_files_from_content_store(checkout)
            if not yaml_files and checkout_path_exists(checkout):
                yaml_files = []
                for file_path in iter_checkout_files(checkout):
                    if file_path.suffix.lower() not in _YAML_SUFFIXES:
                        continue
                    content = read_text(file_path)
                    if content is not None:
                        yaml_files.append((file_path, content))
            for file_path, content in yaml_files:
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
                            # Content store first for config discovery
                            config_files_with_content = (
                                iter_argocd_discovered_config_files_from_content_store(
                                    entry.repo_id,
                                    discovery_path,
                                )
                            )
                            if config_files_with_content:
                                discovered_configs = [
                                    (cfg_path, cfg_content)
                                    for cfg_path, cfg_content in config_files_with_content
                                ]
                            elif target_root is not None:
                                discovered_configs = [
                                    (cfg_path, None)
                                    for cfg_path in iter_argocd_discovered_config_files(
                                        target_root,
                                        discovery_path,
                                    )
                                ]
                            else:
                                continue
                            effective_root = target_root or Path(entry.repo_id)
                            for config_path, config_content in discovered_configs:
                                config_relative = config_relative_path(
                                    config_path, effective_root
                                )
                                environment = infer_environment_from_path(
                                    config_relative
                                )
                                source_refs = argocd_source_references_content_aware(
                                    entry=entry,
                                    config_path=config_path,
                                    config_content=config_content,
                                    target_root=effective_root,
                                    catalog=catalog,
                                    environment=environment,
                                )
                                # Get deploy repo URLs from content or filesystem
                                config_deploy_urls: list[str] = []
                                if config_content is not None:
                                    for doc in load_yaml_documents_from_text(
                                        config_content
                                    ):
                                        config_deploy_urls.extend(
                                            iter_deploy_urls_from_document(doc)
                                        )
                                else:
                                    config_deploy_urls.extend(
                                        iter_argocd_deploy_repo_urls(config_path)
                                    )
                                deploy_repo_urls = list(
                                    dict.fromkeys(
                                        [
                                            *config_deploy_urls,
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
                                        for (
                                            target_entry,
                                            target_alias,
                                        ) in target_matches:
                                            if source_entity_id.startswith(
                                                "workload-subject:"
                                            ) and target_entry.repo_id in {
                                                entry.repo_id,
                                                checkout.logical_repo_id,
                                            }:
                                                continue
                                            if source_entity_id == target_entry.repo_id:
                                                continue
                                            before_deploy = len(evidence)
                                            append_matched_evidence(
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
                                                    "config_path": str(config_relative),
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
                                for (
                                    cluster_name
                                ) in iter_destination_clusters_content_aware(
                                    config_path=config_path,
                                    config_content=config_content,
                                    repo_id=entry.repo_id,
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
                                                "config_path": str(config_relative),
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


__all__ = ["discover_argocd_evidence"]
