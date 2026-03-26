"""ArgoCD-specific helpers for raw file-based relationship evidence extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Iterator

from .file_evidence_support import load_yaml_documents

__all__ = [
    "extract_argocd_subject_name",
    "infer_environment_from_path",
    "iter_argocd_applicationset_source_repo_urls",
    "iter_argocd_deploy_repo_urls",
    "iter_argocd_deployed_repo_identifiers",
    "iter_argocd_destination_cluster_names",
    "iter_argocd_discovered_config_files",
    "iter_argocd_discovery_targets",
]


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

    for document in load_yaml_documents(config_path):
        if not isinstance(document, dict):
            continue
        for key in ("destinationClusterName", "destinationCluster"):
            value = document.get(key)
            if isinstance(value, str) and value.strip():
                yield value.strip()
        destination = document.get("destination")
        if isinstance(destination, dict):
            cluster_name = destination.get("name") or destination.get("clusterName")
            if isinstance(cluster_name, str) and cluster_name.strip():
                yield cluster_name.strip()


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
