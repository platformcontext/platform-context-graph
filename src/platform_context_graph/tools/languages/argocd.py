"""ArgoCD-specific YAML manifest classification and parsing."""

import re
from typing import Any

_ARGOCD_API = "argoproj.io/"
_TEMPLATE_ONLY_PATTERN = re.compile(r"^\s*\{\{.*\}\}\s*$")


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    """Return unique non-empty values while preserving their first appearance."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _is_template_only(value: str) -> bool:
    """Return whether the string is only a template expression."""
    return bool(_TEMPLATE_ONLY_PATTERN.match(value))


def _normalize_source_root(raw_path: str) -> str:
    """Normalize a source path into a stable directory root for linking."""
    segments = [segment for segment in raw_path.strip().split("/") if segment]
    stable_segments: list[str] = []
    for segment in segments:
        if segment in {"*", "**"} or _is_template_only(segment):
            break
        if segment.endswith((".yaml", ".yml", ".json")):
            break
        stable_segments.append(segment)

    cleaned = "/".join(stable_segments).strip("/")
    if not cleaned:
        return ""

    if "overlays" in stable_segments:
        overlay_index = stable_segments.index("overlays")
        if overlay_index == 0:
            return "overlays/"
        return "/".join(stable_segments[:overlay_index]) + "/"
    if "base" in stable_segments:
        base_index = stable_segments.index("base")
        if base_index == 0:
            return "base/"
        return "/".join(stable_segments[:base_index]) + "/"
    return cleaned + "/"


def _collect_generator_sources(
    generator: dict[str, Any],
    *,
    source_repos: list[str],
    source_paths: list[str],
) -> None:
    """Recursively collect repo URLs and paths from ApplicationSet generators."""
    if not isinstance(generator, dict):
        return

    git_generator = generator.get("git")
    if isinstance(git_generator, dict):
        repo_url = str(git_generator.get("repoURL", "")).strip()
        if repo_url and not _is_template_only(repo_url):
            source_repos.append(repo_url)

        for entry in git_generator.get("files", []) or []:
            if isinstance(entry, dict):
                path = str(entry.get("path", "")).strip()
                if path and not _is_template_only(path):
                    source_paths.append(path)

        for entry in git_generator.get("directories", []) or []:
            if isinstance(entry, dict):
                path = str(entry.get("path", "")).strip()
                if path and not _is_template_only(path):
                    source_paths.append(path)

    for value in generator.values():
        if isinstance(value, dict):
            _collect_generator_sources(
                value,
                source_repos=source_repos,
                source_paths=source_paths,
            )
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _collect_generator_sources(
                        item,
                        source_repos=source_repos,
                        source_paths=source_paths,
                    )


def _extract_template_sources(template_spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Extract repo URLs and paths from the ApplicationSet template spec."""
    source_repos: list[str] = []
    source_paths: list[str] = []

    single_source = template_spec.get("source")
    if isinstance(single_source, dict):
        repo_url = str(single_source.get("repoURL", "")).strip()
        source_path = str(single_source.get("path", "")).strip()
        if repo_url and not _is_template_only(repo_url):
            source_repos.append(repo_url)
        if source_path and not _is_template_only(source_path):
            source_paths.append(source_path)

    for source in template_spec.get("sources", []) or []:
        if not isinstance(source, dict):
            continue
        repo_url = str(source.get("repoURL", "")).strip()
        source_path = str(source.get("path", "")).strip()
        if repo_url and not _is_template_only(repo_url):
            source_repos.append(repo_url)
        if source_path and not _is_template_only(source_path):
            source_paths.append(source_path)

    return source_repos, source_paths


def is_argocd_application(api_version: str, kind: str) -> bool:
    """Return whether the document is an ArgoCD Application resource.

    Args:
        api_version: Resource API version.
        kind: Resource kind.

    Returns:
        ``True`` when the resource is an ArgoCD Application.
    """
    return api_version.startswith(_ARGOCD_API) and kind == "Application"


def is_argocd_applicationset(api_version: str, kind: str) -> bool:
    """Return whether the document is an ArgoCD ApplicationSet resource.

    Args:
        api_version: Resource API version.
        kind: Resource kind.

    Returns:
        ``True`` when the resource is an ArgoCD ApplicationSet.
    """
    return api_version.startswith(_ARGOCD_API) and kind == "ApplicationSet"


def parse_argocd_application(
    doc: dict[str, Any],
    metadata: dict[str, Any],
    path: str,
    line_number: int,
    language_name: str,
) -> dict[str, Any]:
    """Parse an ArgoCD Application resource.

    Args:
        doc: Parsed YAML document.
        metadata: Resource metadata.
        path: Source file path.
        line_number: 1-based document start line.
        language_name: Language name to include in the result.

    Returns:
        Parsed ArgoCD Application metadata.
    """
    spec = doc.get("spec", {}) or {}
    source = spec.get("source", {}) or {}
    destination = spec.get("destination", {}) or {}
    return {
        "name": metadata.get("name", ""),
        "line_number": line_number,
        "namespace": metadata.get("namespace", ""),
        "project": spec.get("project", ""),
        "source_repo": source.get("repoURL", ""),
        "source_path": source.get("path", ""),
        "source_revision": source.get("targetRevision", ""),
        "dest_server": destination.get("server", ""),
        "dest_namespace": destination.get("namespace", ""),
        "path": path,
        "lang": language_name,
    }


def parse_argocd_applicationset(
    doc: dict[str, Any],
    metadata: dict[str, Any],
    path: str,
    line_number: int,
    language_name: str,
) -> dict[str, Any]:
    """Parse an ArgoCD ApplicationSet resource.

    Args:
        doc: Parsed YAML document.
        metadata: Resource metadata.
        path: Source file path.
        line_number: 1-based document start line.
        language_name: Language name to include in the result.

    Returns:
        Parsed ArgoCD ApplicationSet metadata.
    """
    spec = doc.get("spec", {}) or {}
    template_spec = ((spec.get("template", {}) or {}).get("spec", {}) or {})
    generator_types: list[str] = []
    source_repos: list[str] = []
    source_paths: list[str] = []
    for generator in spec.get("generators", []) or []:
        if isinstance(generator, dict):
            generator_types.extend(generator.keys())
            _collect_generator_sources(
                generator,
                source_repos=source_repos,
                source_paths=source_paths,
            )

    template_repos, template_paths = _extract_template_sources(template_spec)
    source_repos.extend(template_repos)
    source_paths.extend(template_paths)

    deduped_paths = _dedupe_preserve_order(source_paths)
    source_roots = _dedupe_preserve_order(
        [_normalize_source_root(path) for path in deduped_paths]
    )

    return {
        "name": metadata.get("name", ""),
        "line_number": line_number,
        "namespace": metadata.get("namespace", ""),
        "generators": ",".join(generator_types),
        "project": template_spec.get("project", ""),
        "dest_namespace": (template_spec.get("destination", {}) or {}).get(
            "namespace", ""
        ),
        "source_repos": ",".join(_dedupe_preserve_order(source_repos)),
        "source_paths": ",".join(deduped_paths),
        "source_roots": ",".join(source_roots),
        "path": path,
        "lang": language_name,
    }
