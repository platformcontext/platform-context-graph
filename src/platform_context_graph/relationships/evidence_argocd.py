"""ArgoCD raw file evidence extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Sequence

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
    iter_argocd_discovered_config_files_from_content_store,
    iter_argocd_discovery_targets,
    load_yaml_from_content_store,
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
                                config_relative_path = _config_relative_path(
                                    config_path, effective_root
                                )
                                environment = infer_environment_from_path(
                                    config_relative_path
                                )
                                source_refs = _argocd_source_references_content_aware(
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
                                            _iter_deploy_urls_from_document(doc)
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
                                                    "config_path": str(
                                                        config_relative_path
                                                    ),
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
                                ) in _iter_destination_clusters_content_aware(
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
                                                "config_path": str(
                                                    config_relative_path
                                                ),
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


def _iter_deploy_urls_from_document(document: Any) -> Iterator[str]:
    """Yield deploy-source repository URLs from a parsed config document."""

    if not isinstance(document, dict):
        return
    for config_key in ("git", "helm"):
        nested_config = document.get(config_key)
        if not isinstance(nested_config, dict):
            continue
        repo_url = nested_config.get("repoURL")
        if isinstance(repo_url, str):
            cleaned = repo_url.strip()
            if cleaned:
                yield cleaned


def _argocd_source_references_content_aware(
    *,
    entry: CatalogEntry,
    config_path: Path,
    config_content: str | None,
    target_root: Path,
    catalog: Sequence[CatalogEntry],
    environment: str | None,
) -> list[tuple[str, str, str]]:
    """Return deployable repo references, using content store when available."""

    references: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    # Get deployed repo identifiers from content or filesystem
    if config_content is not None:
        candidates = list(
            _iter_deployed_repo_identifiers_from_content(
                config_path,
                config_content,
                target_root,
            )
        )
    else:
        candidates = list(
            iter_argocd_deployed_repo_identifiers(config_path, target_root)
        )

    for candidate in candidates:
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

    subject_name = None
    if config_content is not None:
        for doc in load_yaml_documents_from_text(config_content):
            if not isinstance(doc, dict):
                continue
            for key in ("name", "addon"):
                value = doc.get(key)
                if isinstance(value, str) and value.strip():
                    subject_name = value.strip()
                    break
            if subject_name:
                break
    else:
        subject_name = extract_argocd_subject_name(config_path)

    subject_name = subject_name or entry.repo_name
    subject = WorkloadSubjectEntity.from_parts(
        repository_id=entry.repo_id,
        subject_type="argocd-config",
        name=subject_name,
        environment=environment,
        path=str(_config_relative_path(config_path, target_root)),
    )
    return [(entry.repo_id, subject.entity_id, "workload-subject")]


def _iter_deployed_repo_identifiers_from_content(
    config_path: Path,
    config_content: str,
    target_root: Path,
) -> Iterator[str]:
    """Yield deployed repo identifiers from parsed content (no filesystem access)."""

    try:
        relative_path = config_path.relative_to(target_root)
    except ValueError:
        relative_path = config_path
    yield str(relative_path)

    for document in load_yaml_documents_from_text(config_content):
        if not isinstance(document, dict):
            continue
        for key in ("addon", "name"):
            value = document.get(key)
            if isinstance(value, str) and value.strip():
                yield value.strip()
        labels = document.get("labels")
        if isinstance(labels, dict):
            for label_key in (
                "app.kubernetes.io/name",
                "app.kubernetes.io/part-of",
            ):
                label_value = labels.get(label_key)
                if isinstance(label_value, str) and label_value.strip():
                    yield label_value.strip()
        git_config = document.get("git")
        if isinstance(git_config, dict):
            overlay_path = git_config.get("overlayPath")
            if isinstance(overlay_path, str) and overlay_path.strip():
                yield overlay_path.strip()


def _iter_destination_clusters_content_aware(
    *,
    config_path: Path,
    config_content: str | None,
    repo_id: str,
) -> Iterator[str]:
    """Yield destination cluster names using content store or filesystem."""

    if config_content is not None:
        # Parse the config itself + look for sibling overlay YAMLs in content store
        yielded: set[str] = set()
        documents = load_yaml_documents_from_text(config_content)
        # Also load sibling YAML files from content store
        config_dir = str(config_path.parent)
        sibling_docs = _load_sibling_yaml_from_content_store(repo_id, config_dir)
        for document in [*documents, *sibling_docs]:
            for cluster_name in _iter_cluster_names_from_document(document):
                if cluster_name not in yielded:
                    yielded.add(cluster_name)
                    yield cluster_name
    else:
        yield from iter_argocd_destination_cluster_names(config_path)


def _load_sibling_yaml_from_content_store(
    repo_id: str,
    directory: str,
) -> list[Any]:
    """Load all YAML documents from sibling files in a directory via content store."""

    from ..content.state import get_postgres_content_provider

    provider = get_postgres_content_provider()
    if provider is None or not provider.enabled:
        return []

    documents: list[Any] = []
    try:
        with provider._cursor() as cursor:
            cursor.execute(
                """
                SELECT content
                FROM content_files
                WHERE repo_id = %(repo_id)s
                  AND relative_path LIKE %(dir_pattern)s
                  AND (relative_path LIKE '%%.yaml' OR relative_path LIKE '%%.yml')
                  AND relative_path NOT LIKE '%%/%%/%%'
                  AND content IS NOT NULL
                """,
                {
                    "repo_id": repo_id,
                    "dir_pattern": directory + "/%",
                },
            )
            for row in cursor:
                content = row["content"]
                if content:
                    documents.extend(load_yaml_documents_from_text(content))
    except Exception:
        pass
    return documents


def _iter_cluster_names_from_document(node: Any) -> Iterator[str]:
    """Yield concrete cluster names from one YAML document recursively."""

    _CLUSTER_KEYS = {
        "cluster",
        "clustername",
        "destinationcluster",
        "destinationclustername",
    }
    _IGNORED = {"placeholder", "{{.cluster}}", "{{.clustername}}", "{{.environment}}"}

    if isinstance(node, dict):
        destination = node.get("destination")
        if isinstance(destination, dict):
            for value in (
                destination.get("name"),
                destination.get("clusterName"),
                destination.get("cluster"),
            ):
                if (
                    isinstance(value, str)
                    and value.strip()
                    and value.strip().lower() not in _IGNORED
                ):
                    yield value.strip()
        for key, value in node.items():
            if str(key).lower() in _CLUSTER_KEYS and isinstance(value, str):
                cleaned = value.strip()
                if cleaned and cleaned.lower() not in _IGNORED:
                    yield cleaned
            yield from _iter_cluster_names_from_document(value)
        return
    if isinstance(node, list):
        for item in node:
            yield from _iter_cluster_names_from_document(item)


__all__ = ["discover_argocd_evidence"]
