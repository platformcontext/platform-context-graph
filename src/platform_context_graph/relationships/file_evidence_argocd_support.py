"""ArgoCD-specific helpers for raw file-based relationship evidence extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Iterator

from .file_evidence_support import load_yaml_documents, load_yaml_documents_from_text

__all__ = [
    "extract_argocd_subject_name",
    "infer_environment_from_path",
    "iter_argocd_applicationset_source_repo_urls",
    "iter_argocd_deploy_repo_urls",
    "iter_argocd_deployed_repo_identifiers",
    "iter_argocd_destination_cluster_names",
    "iter_argocd_discovered_config_files",
    "iter_argocd_discovered_config_files_from_content_store",
    "iter_argocd_discovery_targets",
    "load_yaml_from_content_store",
]

_CLUSTER_VALUE_KEYS = {
    "cluster",
    "clustername",
    "destinationcluster",
    "destinationclustername",
}
_IGNORED_CLUSTER_VALUES = {
    "placeholder",
    "{{.cluster}}",
    "{{.clustername}}",
    "{{.environment}}",
}


def iter_argocd_discovery_targets(document: Any) -> Iterator[tuple[str, str]]:
    """Yield ApplicationSet repo URLs and discovery paths for git file generators."""

    if not isinstance(document, dict):
        return
    if document.get("kind") != "ApplicationSet":
        return
    spec = document.get("spec")
    if not isinstance(spec, dict):
        return
    for git_generator in _iter_argocd_git_generators(spec.get("generators", []) or []):
        repo_url = git_generator.get("repoURL")
        if not isinstance(repo_url, str) or not repo_url.strip():
            continue
        for file_entry in git_generator.get("files", []) or []:
            if not isinstance(file_entry, dict):
                continue
            discovery_path = file_entry.get("path")
            if not isinstance(discovery_path, str):
                continue
            if "config.yaml" not in discovery_path.lower():
                continue
            yield repo_url.strip(), discovery_path.strip()


def iter_argocd_discovered_config_files(
    target_root: Path,
    discovery_path: str,
) -> Iterator[Path]:
    """Yield discovered config files inside the target checkout."""

    try:
        yield from (
            path
            for path in target_root.glob(discovery_path)
            if path.is_file() and path.name.lower() == "config.yaml"
        )
    except (OSError, ValueError):
        return


def iter_argocd_deploy_repo_urls(config_path: Path) -> Iterator[str]:
    """Yield deploy-source repository URLs from a discovered config file."""

    for document in load_yaml_documents(config_path):
        if not isinstance(document, dict):
            continue
        for config_key in ("git", "helm"):
            nested_config = document.get(config_key)
            if not isinstance(nested_config, dict):
                continue
            repo_url = nested_config.get("repoURL")
            if isinstance(repo_url, str):
                cleaned = repo_url.strip()
                if cleaned:
                    yield cleaned


def iter_argocd_applicationset_source_repo_urls(document: Any) -> Iterator[str]:
    """Yield ApplicationSet template source repository URLs."""

    if not isinstance(document, dict) or document.get("kind") != "ApplicationSet":
        return
    spec = document.get("spec")
    if not isinstance(spec, dict):
        return
    template = spec.get("template")
    if not isinstance(template, dict):
        return
    template_spec = template.get("spec")
    if not isinstance(template_spec, dict):
        return
    single_source = template_spec.get("source")
    if isinstance(single_source, dict):
        repo_url = single_source.get("repoURL")
        if isinstance(repo_url, str) and repo_url.strip():
            yield repo_url.strip()
    for source in template_spec.get("sources", []) or []:
        if not isinstance(source, dict):
            continue
        repo_url = source.get("repoURL")
        if isinstance(repo_url, str) and repo_url.strip():
            yield repo_url.strip()


def iter_argocd_destination_cluster_names(config_path: Path) -> Iterator[str]:
    """Yield destination cluster names from one discovered ArgoCD config file."""

    yielded: set[str] = set()
    for yaml_path in _iter_related_overlay_yaml_files(config_path):
        for document in load_yaml_documents(yaml_path):
            for cluster_name in _iter_cluster_names(document):
                if cluster_name in yielded:
                    continue
                yielded.add(cluster_name)
                yield cluster_name


def infer_environment_from_path(path: Path) -> str | None:
    """Infer an environment hint from a config or overlay path when portable."""

    for index, part in enumerate(path.parts[:-1]):
        if part.lower() == "overlays" and index + 1 < len(path.parts) - 1:
            candidate = path.parts[index + 1].strip()
            if candidate:
                return candidate
    return None


def iter_argocd_deployed_repo_identifiers(
    config_path: Path,
    target_root: Path,
) -> Iterator[str]:
    """Yield strings that can identify the repo deployed by one discovered config."""

    try:
        relative_path = config_path.relative_to(target_root)
    except ValueError:
        relative_path = config_path
    yield str(relative_path)

    for document in load_yaml_documents(config_path):
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


def extract_argocd_subject_name(config_path: Path) -> str | None:
    """Extract a stable non-repo deployable name from one discovered config file."""

    for document in load_yaml_documents(config_path):
        if not isinstance(document, dict):
            continue
        for key in ("name", "addon"):
            value = document.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        labels = document.get("labels")
        if isinstance(labels, dict):
            for label_key in ("app.kubernetes.io/name", "app.kubernetes.io/part-of"):
                label_value = labels.get(label_key)
                if isinstance(label_value, str) and label_value.strip():
                    return label_value.strip()
    return None


def iter_argocd_discovered_config_files_from_content_store(
    repo_id: str,
    discovery_path: str,
) -> list[tuple[Path, str]]:
    """Discover ArgoCD config files from the content store.

    Replaces filesystem glob against a target checkout with a Postgres query
    that matches the discovery path pattern against indexed file paths.

    Args:
        repo_id: Canonical repository identifier for the target repo.
        discovery_path: Glob pattern from ApplicationSet (e.g. ``argocd/*/overlays/*/config.yaml``).

    Returns:
        List of (synthetic_path, content) pairs for matching config files.
    """

    from ..content.state import get_postgres_content_provider

    provider = get_postgres_content_provider()
    if provider is None or not provider.enabled:
        return []

    sql_pattern = discovery_path.replace("*", "%")
    if not sql_pattern.endswith("%"):
        pass

    results: list[tuple[Path, str]] = []
    try:
        with provider._cursor() as cursor:
            cursor.execute(
                """
                SELECT relative_path, content
                FROM content_files
                WHERE repo_id = %(repo_id)s
                  AND relative_path LIKE %(pattern)s
                  AND lower(relative_path) LIKE '%%config.yaml'
                  AND content IS NOT NULL
                """,
                {"repo_id": repo_id, "pattern": sql_pattern},
            )
            for row in cursor:
                relative_path = row["relative_path"]
                content = row["content"]
                if content:
                    results.append((Path(relative_path), content))
    except Exception:
        return []

    return results


def load_yaml_from_content_store(
    repo_id: str,
    relative_path: str,
) -> list[Any]:
    """Load YAML documents for one file from the content store.

    This is the content-store equivalent of ``load_yaml_documents(path)``
    for use when file paths reference content inside a repo that isn't
    cloned locally.

    Args:
        repo_id: Canonical repository identifier.
        relative_path: Repo-relative file path.

    Returns:
        Parsed YAML documents, or empty list on failure.
    """

    from ..content.state import get_postgres_content_provider

    provider = get_postgres_content_provider()
    if provider is None or not provider.enabled:
        return []

    try:
        with provider._cursor() as cursor:
            cursor.execute(
                """
                SELECT content
                FROM content_files
                WHERE repo_id = %(repo_id)s
                  AND relative_path = %(relative_path)s
                  AND content IS NOT NULL
                """,
                {"repo_id": repo_id, "relative_path": relative_path},
            )
            row = cursor.fetchone()
            if row is None:
                return []
            return load_yaml_documents_from_text(row["content"])
    except Exception:
        return []


def _iter_argocd_git_generators(
    generators: Iterable[Any],
) -> Iterator[dict[str, Any]]:
    """Yield git generators from nested ApplicationSet generator definitions."""

    for generator in generators:
        if not isinstance(generator, dict):
            continue
        git_generator = generator.get("git")
        if isinstance(git_generator, dict):
            yield git_generator
        for nested_key in ("matrix", "merge"):
            nested = generator.get(nested_key)
            if not isinstance(nested, dict):
                continue
            nested_generators = nested.get("generators")
            if isinstance(nested_generators, list):
                yield from _iter_argocd_git_generators(nested_generators)


def _iter_related_overlay_yaml_files(config_path: Path) -> Iterator[Path]:
    """Yield the discovered config and sibling overlay YAML files."""

    yielded: set[Path] = set()
    for candidate in [config_path, *sorted(config_path.parent.glob("*.y*ml"))]:
        if not candidate.is_file() or candidate in yielded:
            continue
        yielded.add(candidate)
        yield candidate


def _iter_cluster_names(node: Any) -> Iterator[str]:
    """Yield concrete cluster names from one YAML document recursively."""

    if isinstance(node, dict):
        destination = node.get("destination")
        if isinstance(destination, dict):
            for value in (
                destination.get("name"),
                destination.get("clusterName"),
                destination.get("cluster"),
            ):
                cleaned = _normalize_cluster_value(value)
                if cleaned:
                    yield cleaned
        for key, value in node.items():
            cleaned = (
                _normalize_cluster_value(value)
                if str(key).lower() in _CLUSTER_VALUE_KEYS
                else None
            )
            if cleaned:
                yield cleaned
            yield from _iter_cluster_names(value)
        return
    if isinstance(node, list):
        for item in node:
            yield from _iter_cluster_names(item)


def _normalize_cluster_value(value: Any) -> str | None:
    """Return a stable cluster value or ``None`` when it is placeholder-like."""

    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.lower() in _IGNORED_CLUSTER_VALUES:
        return None
    return cleaned
