"""Support helpers for ArgoCD evidence extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Sequence

from .entities import WorkloadSubjectEntity
from .file_evidence_argocd_support import (
    extract_argocd_subject_name,
    iter_argocd_deployed_repo_identifiers,
    iter_argocd_destination_cluster_names,
)
from .file_evidence_support import (
    CatalogEntry,
    load_yaml_documents_from_text,
    match_catalog,
)
from .models import RelationshipEvidenceFact


def append_matched_evidence(
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


def config_relative_path(config_path: Path, target_root: Path) -> Path:
    """Return the repo-relative path when possible."""
    try:
        return config_path.relative_to(target_root)
    except ValueError:
        return config_path


def iter_deploy_urls_from_document(document: Any) -> Iterator[str]:
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


def argocd_source_references_content_aware(
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
    candidates = (
        list(
            iter_deployed_repo_identifiers_from_content(
                config_path,
                config_content,
                target_root,
            )
        )
        if config_content is not None
        else list(iter_argocd_deployed_repo_identifiers(config_path, target_root))
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

    subject_name = _subject_name_from_content(config_content)
    if subject_name is None:
        subject_name = extract_argocd_subject_name(config_path)
    subject = WorkloadSubjectEntity.from_parts(
        repository_id=entry.repo_id,
        subject_type="argocd-config",
        name=subject_name or entry.repo_name,
        environment=environment,
        path=str(config_relative_path(config_path, target_root)),
    )
    return [(entry.repo_id, subject.entity_id, "workload-subject")]


def iter_deployed_repo_identifiers_from_content(
    config_path: Path,
    config_content: str,
    target_root: Path,
) -> Iterator[str]:
    """Yield deployed repo identifiers from parsed content without filesystem access."""
    yield str(config_relative_path(config_path, target_root))

    for document in load_yaml_documents_from_text(config_content):
        if not isinstance(document, dict):
            continue
        for key in ("addon", "name"):
            value = document.get(key)
            if isinstance(value, str) and value.strip():
                yield value.strip()
        labels = document.get("labels")
        if isinstance(labels, dict):
            for label_key in ("app.kubernetes.io/name", "app.kubernetes.io/part-of"):
                label_value = labels.get(label_key)
                if isinstance(label_value, str) and label_value.strip():
                    yield label_value.strip()
        git_config = document.get("git")
        if isinstance(git_config, dict):
            overlay_path = git_config.get("overlayPath")
            if isinstance(overlay_path, str) and overlay_path.strip():
                yield overlay_path.strip()


def iter_destination_clusters_content_aware(
    *,
    config_path: Path,
    config_content: str | None,
    repo_id: str,
) -> Iterator[str]:
    """Yield destination cluster names using content store or filesystem."""
    if config_content is None:
        yield from iter_argocd_destination_cluster_names(config_path)
        return

    yielded: set[str] = set()
    documents = load_yaml_documents_from_text(config_content)
    sibling_docs = load_sibling_yaml_from_content_store(
        repo_id, str(config_path.parent)
    )
    for document in [*documents, *sibling_docs]:
        for cluster_name in iter_cluster_names_from_document(document):
            if cluster_name in yielded:
                continue
            yielded.add(cluster_name)
            yield cluster_name


def load_sibling_yaml_from_content_store(repo_id: str, directory: str) -> list[Any]:
    """Load sibling YAML documents in a directory via the content store."""
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
                  AND SUBSTRING(relative_path FROM CHAR_LENGTH(%(dir_prefix)s) + 1) NOT LIKE '%%/%%/%%'
                  AND content IS NOT NULL
                """,
                {
                    "repo_id": repo_id,
                    "dir_pattern": directory + "/%",
                    "dir_prefix": directory + "/",
                },
            )
            for row in cursor:
                content = row["content"]
                if content:
                    documents.extend(load_yaml_documents_from_text(content))
    except Exception:
        pass
    return documents


def iter_cluster_names_from_document(node: Any) -> Iterator[str]:
    """Yield concrete cluster names from one YAML document recursively."""
    cluster_keys = {
        "cluster",
        "clustername",
        "destinationcluster",
        "destinationclustername",
    }
    ignored = {"placeholder", "{{.cluster}}", "{{.clustername}}", "{{.environment}}"}

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
                    and value.strip().lower() not in ignored
                ):
                    yield value.strip()
        for key, value in node.items():
            if str(key).lower() in cluster_keys and isinstance(value, str):
                cleaned = value.strip()
                if cleaned and cleaned.lower() not in ignored:
                    yield cleaned
            yield from iter_cluster_names_from_document(value)
        return
    if isinstance(node, list):
        for item in node:
            yield from iter_cluster_names_from_document(item)


def _subject_name_from_content(config_content: str | None) -> str | None:
    """Extract a stable subject name from config content when one is declared."""

    if config_content is None:
        return None
    for doc in load_yaml_documents_from_text(config_content):
        if not isinstance(doc, dict):
            continue
        for key in ("name", "addon"):
            value = doc.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None
