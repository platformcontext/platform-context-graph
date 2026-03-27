"""Content-backed repository context enrichment for API surface and hostnames."""

from __future__ import annotations

import json
import re
from glob import glob
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from ...query import content as content_queries
from .common import get_db_manager, resolve_repository
from .content_enrichment_delivery_paths import summarize_delivery_paths
from .content_enrichment_openapi import dedupe_endpoint_rows, extract_openapi_endpoints
from .content_enrichment_workflows import extract_delivery_workflows

_SPEC_CANDIDATES = (
    "server/init/plugins/spec.js",
    "server/init/plugins/spec.ts",
    "redocly.yaml",
    "versioning.config.ts",
    "versioning.config.js",
    "catalog-info.yaml",
    "catalog-specs.yaml",
)
_HOSTNAME_CANDIDATES = (
    "config/qa.json",
    "config/production.json",
    "config/development.json",
    "config/dev.json",
    "cypress.config.ts",
    "cypress.config.js",
)
_BASE_URL_RE = re.compile(r"baseUrl:\s*['\"]https?://([^/'\"]+)")
_DOCS_ROUTE_RE = re.compile(r"path:\s*['\"]([^'\"]+)['\"]")
_DEFAULT_VERSION_RE = re.compile(
    r"default(?:Api)?Version\s*:\s*['\"]([^'\"]+)['\"]"
)
_MAX_API_SURFACE_ENDPOINTS = 25


def enrich_repository_context(database: Any, context: dict[str, Any]) -> dict[str, Any]:
    """Add API surface and hostname hints to a repository context payload."""

    repository = context.get("repository") or {}
    repo_id = repository.get("id")
    if not isinstance(repo_id, str) or not repo_id:
        return context

    api_surface = _extract_api_surface(database, repo_id=repo_id)
    hostnames = _extract_hostnames(
        database,
        repo_id=repo_id,
        repo_name=str(repository.get("name") or ""),
        deploys_from=context.get("deploys_from") or [],
        discovers_config_in=context.get("discovers_config_in") or [],
    )
    if api_surface:
        context["api_surface"] = api_surface
    if hostnames:
        context["hostnames"] = hostnames
        observed_environments = _observed_config_environments(hostnames)
        if observed_environments:
            context["observed_config_environments"] = observed_environments
        _remove_limitation(context, "dns_unknown")
    db_manager = get_db_manager(database)

    def _resolve_repo(candidate: str) -> dict[str, Any] | None:
        """Resolve one related repository candidate through the graph database."""

        with db_manager.get_driver().session() as session:
            return _resolve_related_repo(session, candidate)

    delivery_workflows = extract_delivery_workflows(
        repository=repository,
        resolve_repository=_resolve_repo,
    )
    if delivery_workflows:
        context["delivery_workflows"] = delivery_workflows
        delivery_paths = summarize_delivery_paths(
            delivery_workflows=delivery_workflows,
            platforms=list(context.get("platforms") or []),
            deploys_from=list(context.get("deploys_from") or []),
            discovers_config_in=list(context.get("discovers_config_in") or []),
            provisioned_by=list(context.get("provisioned_by") or []),
        )
        if delivery_paths:
            context["delivery_paths"] = delivery_paths
    return context


def _extract_api_surface(database: Any, *, repo_id: str) -> dict[str, Any]:
    """Extract API surface hints from known spec and version files."""

    spec_files: list[dict[str, Any]] = []
    docs_routes: list[str] = []
    api_versions: list[str] = []
    endpoints: list[dict[str, Any]] = []
    for relative_path in _SPEC_CANDIDATES:
        content = _load_repo_file(database, repo_id=repo_id, relative_path=relative_path)
        if content is None:
            continue
        if "specs/index.yaml" in content:
            spec_files.append(
                {
                    "relative_path": "specs/index.yaml",
                    "discovered_from": relative_path,
                }
            )
        if relative_path in {"server/init/plugins/spec.js", "server/init/plugins/spec.ts"}:
            docs_routes.extend(_DOCS_ROUTE_RE.findall(content))
        if relative_path.startswith("versioning.config."):
            api_versions.extend(_DEFAULT_VERSION_RE.findall(content))
    for spec_file in _dedupe_spec_files(spec_files):
        endpoints.extend(
            extract_openapi_endpoints(
                database,
                repo_id=repo_id,
                relative_path=spec_file["relative_path"],
                load_repo_file=_load_repo_file,
            )
        )
        if len(endpoints) >= _MAX_API_SURFACE_ENDPOINTS:
            break
    deduped_endpoints = dedupe_endpoint_rows(endpoints)
    return {
        "spec_files": _dedupe_spec_files(spec_files),
        "docs_routes": _dedupe_strings(docs_routes),
        "api_versions": _dedupe_strings(api_versions),
        "endpoint_count": len(deduped_endpoints),
        "endpoints": deduped_endpoints[:_MAX_API_SURFACE_ENDPOINTS],
    }


def _extract_hostnames(
    database: Any,
    *,
    repo_id: str,
    repo_name: str,
    deploys_from: list[dict[str, Any]],
    discovers_config_in: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract public and internal hostnames from repo and related config repos."""

    hostnames: list[dict[str, Any]] = []
    for relative_path in _HOSTNAME_CANDIDATES:
        content = _load_repo_file(database, repo_id=repo_id, relative_path=relative_path)
        if content is None:
            continue
        if relative_path.endswith(".json"):
            hostnames.extend(
                _hostname_records_from_json(
                    repo_name=repo_name,
                    relative_path=relative_path,
                    content=content,
                )
            )
        else:
            hostnames.extend(
                _hostname_records_from_base_urls(
                    repo_name=repo_name,
                    relative_path=relative_path,
                    content=content,
                )
            )
    hostnames.extend(
        _extract_related_config_hostnames(
            database,
            repo_name=repo_name,
            deploys_from=deploys_from,
            discovers_config_in=discovers_config_in,
        )
    )
    return _dedupe_hostname_rows(hostnames)


def _extract_related_config_hostnames(
    database: Any,
    *,
    repo_name: str,
    deploys_from: list[dict[str, Any]],
    discovers_config_in: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract hostname hints from related config repositories."""

    related_hostnames: list[dict[str, Any]] = []
    db_manager = get_db_manager(database)
    related_rows = list(deploys_from) + list(discovers_config_in)
    with db_manager.get_driver().session() as session:
        for row in related_rows:
            repo_candidates = _split_csv(row.get("source_repos"))
            if not repo_candidates and isinstance(row.get("name"), str):
                repo_candidates = [str(row["name"])]
            for source_repo in repo_candidates:
                resolved_repo = _resolve_related_repo(session, source_repo)
                if resolved_repo is None:
                    continue
                local_path = resolved_repo.get("local_path") or resolved_repo.get("path")
                if not isinstance(local_path, str) or not local_path:
                    continue
                for source_path in _split_csv(row.get("source_paths")):
                    if not source_path:
                        continue
                    candidate_patterns = _values_path_patterns(source_path)
                    for candidate_pattern in candidate_patterns:
                        for file_path in sorted(glob(str(Path(local_path) / candidate_pattern))):
                            file_content = Path(file_path).read_text(encoding="utf-8")
                            relative_path = str(Path(file_path).resolve().relative_to(Path(local_path).resolve()))
                            related_hostnames.extend(
                                _hostname_records_from_yaml(
                                    repo_name=repo_name,
                                    source_repo_name=str(resolved_repo.get("name") or ""),
                                    relative_path=relative_path,
                                    content=file_content,
                                )
                            )
    return related_hostnames


def _remove_limitation(context: dict[str, Any], limitation: str) -> None:
    """Remove one limitation code from a repository context payload."""

    limitations = context.get("limitations")
    if not isinstance(limitations, list):
        return
    context["limitations"] = [item for item in limitations if item != limitation]


def _load_repo_file(database: Any, *, repo_id: str, relative_path: str) -> str | None:
    """Load one repo-relative file through the content service."""

    result = content_queries.get_file_content(
        database,
        repo_id=repo_id,
        relative_path=relative_path,
    )
    if not result.get("available"):
        return None
    content = result.get("content")
    return content if isinstance(content, str) else None

def _hostname_records_from_json(
    *, repo_name: str, relative_path: str, content: str
) -> list[dict[str, Any]]:
    """Extract hostname keys from a JSON config file."""

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return []
    environment = Path(relative_path).stem
    records: list[dict[str, Any]] = []
    for hostname in _collect_key_values(parsed, key="hostname"):
        records.append(
            {
                "hostname": _normalize_hostname(hostname),
                "environment": environment,
                "source_repo": repo_name,
                "relative_path": relative_path,
                "visibility": "public",
            }
        )
    return [record for record in records if record["hostname"]]


def _hostname_records_from_base_urls(
    *, repo_name: str, relative_path: str, content: str
) -> list[dict[str, Any]]:
    """Extract hostnames from JS/TS config files with base URLs."""

    return [
        {
            "hostname": hostname,
            "environment": None,
            "source_repo": repo_name,
            "relative_path": relative_path,
            "visibility": "public",
        }
        for hostname in _BASE_URL_RE.findall(content)
    ]


def _hostname_records_from_yaml(
    *,
    repo_name: str,
    source_repo_name: str,
    relative_path: str,
    content: str,
) -> list[dict[str, Any]]:
    """Extract hostname hints from YAML config values."""

    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError:
        return []
    environment = _infer_environment_from_path(relative_path)
    values = _collect_key_values(parsed, key="hostnames")
    records: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, list):
            for hostname in value:
                normalized = _normalize_hostname(hostname)
                if normalized:
                    records.append(
                        {
                            "hostname": normalized,
                            "environment": environment,
                            "source_repo": source_repo_name,
                            "service_repo": repo_name,
                            "relative_path": relative_path,
                            "visibility": "internal",
                        }
                    )
    return records


def _collect_key_values(node: Any, *, key: str) -> list[Any]:
    """Collect all values stored under a key within a nested object tree."""

    values: list[Any] = []
    if isinstance(node, dict):
        for current_key, current_value in node.items():
            if current_key == key:
                values.append(current_value)
            values.extend(_collect_key_values(current_value, key=key))
    elif isinstance(node, list):
        for item in node:
            values.extend(_collect_key_values(item, key=key))
    return values


def _resolve_related_repo(session: Any, source_repo: str) -> dict[str, Any] | None:
    """Resolve a related repo URL or name to an indexed repository row."""

    candidates = [source_repo]
    parsed = urlparse(source_repo)
    if parsed.path:
        repo_name = parsed.path.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        candidates.append(repo_name)
    for candidate in candidates:
        resolved = resolve_repository(session, candidate)
        if resolved is not None:
            return resolved
    return None


def _values_path_patterns(source_path: str) -> list[str]:
    """Return related values-file glob patterns for one source path hint."""

    normalized = source_path.strip()
    if not normalized:
        return []
    if normalized.endswith("config.yaml"):
        return [normalized[:-len("config.yaml")] + "values.yaml"]
    if normalized.endswith("config.yml"):
        return [normalized[:-len("config.yml")] + "values.yaml"]
    if normalized.endswith(".yaml") or normalized.endswith(".yml"):
        return [normalized]
    return [str(Path(normalized) / "values.yaml")]


def _infer_environment_from_path(relative_path: str) -> str | None:
    """Infer environment name from a repo-relative path."""

    for part in Path(relative_path).parts:
        normalized = part.strip()
        if normalized in {"dev", "development", "prod", "production", "qa", "staging"}:
            return normalized
        if normalized.startswith("bg-"):
            return normalized
    return None


def _normalize_hostname(value: Any) -> str | None:
    """Normalize one hostname-like value."""

    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if "://" in candidate:
        parsed = urlparse(candidate)
        candidate = parsed.netloc or parsed.path
    return candidate or None


def _split_csv(value: Any) -> list[str]:
    """Split a comma-delimited string field into trimmed items."""

    if not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _dedupe_strings(values: list[str]) -> list[str]:
    """Return unique strings in input order."""

    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _dedupe_dict_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique mapping rows in input order."""

    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(sorted((str(k), repr(v)) for k, v in row.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _dedupe_hostname_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one preferred hostname record per hostname in input order."""

    preferred: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        hostname = str(row.get("hostname") or "").strip()
        if not hostname:
            continue
        if hostname not in preferred:
            order.append(hostname)
            preferred[hostname] = row
            continue
        if _hostname_priority(row) > _hostname_priority(preferred[hostname]):
            preferred[hostname] = row
    return [preferred[hostname] for hostname in order]


def _hostname_priority(row: dict[str, Any]) -> int:
    """Return the preference score for one hostname record."""

    score = 0
    if row.get("environment"):
        score += 100
    if row.get("service_repo"):
        score += 20
    if row.get("visibility") == "internal":
        score += 10
    relative_path = str(row.get("relative_path") or "")
    if relative_path.endswith((".json", ".yaml", ".yml")):
        score += 5
    return score


def _observed_config_environments(rows: list[dict[str, Any]]) -> list[str]:
    """Return unique environment names observed in hostname-bearing config."""

    seen: set[str] = set()
    ordered: list[str] = []
    for row in rows:
        environment = row.get("environment")
        if not isinstance(environment, str) or not environment.strip():
            continue
        normalized = environment.strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _dedupe_spec_files(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one spec-file row per relative path, preserving first discovery."""

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        relative_path = str(row.get("relative_path") or "")
        if relative_path in seen:
            continue
        seen.add(relative_path)
        deduped.append(row)
    return deduped
