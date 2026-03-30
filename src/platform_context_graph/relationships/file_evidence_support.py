"""Shared support helpers for raw file-based relationship evidence extraction."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterator, Sequence

import yaml

from .models import RelationshipEvidenceFact, RepositoryCheckout

_SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".idea",
    ".terraform",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
_TERRAFORM_SUFFIXES = (".tf", ".tfvars", ".hcl")
_TERRAFORM_JSON_SUFFIXES = (".tfvars.json",)
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9._/-]+")


@dataclass(slots=True, frozen=True)
class CatalogEntry:
    """One unique repository target and the aliases that can identify it."""

    repo_id: str
    repo_name: str
    aliases: tuple[str, ...]


def build_catalog(checkouts: Sequence[RepositoryCheckout]) -> list[CatalogEntry]:
    """Build a unique alias catalog for referenced repositories."""

    alias_map: dict[str, set[str]] = defaultdict(set)
    by_repo_id: dict[str, set[str]] = defaultdict(set)
    repo_names: dict[str, str] = {}
    for checkout in checkouts:
        repo_names[checkout.logical_repo_id] = checkout.repo_name
        for alias in aliases_for_checkout(checkout):
            alias_map[alias].add(checkout.logical_repo_id)
            by_repo_id[checkout.logical_repo_id].add(alias)

    entries: list[CatalogEntry] = []
    for repo_id, aliases in by_repo_id.items():
        unique_aliases = sorted(
            alias
            for alias in aliases
            if len(alias_map[alias]) == 1 and alias_map[alias] == {repo_id}
        )
        if not unique_aliases:
            continue
        entries.append(
            CatalogEntry(
                repo_id=repo_id,
                repo_name=repo_names[repo_id],
                aliases=tuple(unique_aliases),
            )
        )
    entries.sort(key=lambda item: item.repo_name)
    return entries


def aliases_for_checkout(checkout: RepositoryCheckout) -> set[str]:
    """Return matchable aliases for one checkout."""

    aliases = {checkout.repo_name.lower()}
    if checkout.repo_slug:
        repo_slug = checkout.repo_slug.lower().rstrip("/")
        aliases.add(repo_slug)
        aliases.add(repo_slug.rsplit("/", 1)[-1])
    if checkout.remote_url:
        remote = checkout.remote_url.lower().rstrip("/")
        aliases.add(remote)
        if remote.endswith(".git"):
            aliases.add(remote[:-4])
    return {alias for alias in aliases if alias}


def iter_checkout_files(checkout: RepositoryCheckout) -> Iterator[Path]:
    """Yield relevant files beneath one checkout while skipping bulky directories."""

    if not checkout.checkout_path:
        return
    root = Path(checkout.checkout_path)
    if not root.is_dir():
        return
    for path in root.rglob("*"):
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.is_file():
            yield path


def checkout_path_exists(checkout: RepositoryCheckout) -> bool:
    """Return whether the checkout's local path exists on disk."""

    if not checkout.checkout_path:
        return False
    return Path(checkout.checkout_path).is_dir()


def iter_terraform_files_from_content_store(
    checkout: RepositoryCheckout,
) -> list[tuple[Path, str]]:
    """Load Terraform files from the Postgres content store.

    The content store is the authoritative source for indexed file content.
    This reads Terraform/Terragrunt files directly from Postgres rather
    than walking the filesystem.

    Args:
        checkout: Repository checkout record with ``logical_repo_id``.

    Returns:
        List of (synthetic_path, content) pairs for Terraform files.
    """

    from ..content.state import get_postgres_content_provider

    provider = get_postgres_content_provider()
    if provider is None or not provider.enabled:
        return []

    repo_id = checkout.logical_repo_id
    terraform_files: list[tuple[Path, str]] = []

    try:
        with provider._cursor() as cursor:
            cursor.execute(
                """
                SELECT relative_path, content
                FROM content_files
                WHERE repo_id = %(repo_id)s
                  AND (
                    relative_path LIKE '%%.tf'
                    OR relative_path LIKE '%%.tfvars'
                    OR relative_path LIKE '%%.hcl'
                  )
                  AND content IS NOT NULL
                """,
                {"repo_id": repo_id},
            )
            for row in cursor:
                relative_path = row["relative_path"]
                content = row["content"]
                if content:
                    base = checkout.checkout_path or repo_id
                    synthetic_path = Path(base) / relative_path
                    terraform_files.append((synthetic_path, content))
    except Exception:
        return []

    return terraform_files


def is_terraform_file(path: Path) -> bool:
    """Return whether the path should be scanned as Terraform/Terragrunt."""

    lower_name = path.name.lower()
    if lower_name.endswith(_TERRAFORM_JSON_SUFFIXES):
        return True
    return lower_name.endswith(_TERRAFORM_SUFFIXES)


def read_text(path: Path) -> str | None:
    """Read UTF-8 text while tolerating unreadable files."""

    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def load_yaml_documents(path: Path) -> list[Any]:
    """Load YAML documents from one file, returning an empty list on parse failures."""

    content = read_text(path)
    if content is None or not content.strip():
        return []
    return load_yaml_documents_from_text(content)


def load_yaml_documents_from_text(content: str) -> list[Any]:
    """Load YAML documents from raw text, returning an empty list on parse failures."""

    if not content.strip():
        return []
    try:
        return [doc for doc in yaml.safe_load_all(content) if doc is not None]
    except yaml.YAMLError:
        return []


def iter_yaml_strings(value: Any) -> Iterator[str]:
    """Yield string leaves from a YAML-loaded structure."""

    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            yield stripped
        return
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_yaml_strings(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from iter_yaml_strings(child)


def iter_kustomize_resource_strings(document: Any) -> Iterator[str]:
    """Yield resource-like Kustomize references from a parsed document."""

    if not isinstance(document, dict):
        return
    for key in ("resources", "components"):
        for value in document.get(key, []) or []:
            if isinstance(value, str):
                yield value


def iter_kustomize_helm_strings(document: Any) -> Iterator[str]:
    """Yield Helm-related Kustomize references from a parsed document."""

    if not isinstance(document, dict):
        return
    for item in document.get("helmCharts", []) or []:
        if not isinstance(item, dict):
            continue
        for key in ("name", "repo", "releaseName"):
            value = item.get(key)
            if isinstance(value, str):
                yield value


def iter_kustomize_image_strings(document: Any) -> Iterator[str]:
    """Yield image-related Kustomize references from a parsed document."""

    if not isinstance(document, dict):
        return
    for item in document.get("images", []) or []:
        if not isinstance(item, dict):
            continue
        for key in ("name", "newName"):
            value = item.get(key)
            if isinstance(value, str):
                yield value


def append_evidence_for_candidate(
    *,
    evidence: list[RelationshipEvidenceFact],
    seen: set[tuple[str, str, str, str]],
    catalog: Sequence[CatalogEntry],
    source_repo_id: str,
    candidate: str,
    evidence_kind: str,
    relationship_type: str = "DEPENDS_ON",
    confidence: float,
    rationale: str,
    path: Path,
    extractor: str,
    extra_details: dict[str, Any] | None = None,
) -> None:
    """Append one evidence fact when a candidate string identifies a unique target repo."""

    for entry, matched_alias in match_catalog(candidate, catalog):
        if entry.repo_id == source_repo_id:
            continue
        key = (evidence_kind, source_repo_id, entry.repo_id, str(path))
        if key in seen:
            continue
        seen.add(key)
        evidence.append(
            RelationshipEvidenceFact(
                evidence_kind=evidence_kind,
                relationship_type=relationship_type,
                source_repo_id=source_repo_id,
                target_repo_id=entry.repo_id,
                confidence=confidence,
                rationale=rationale,
                details={
                    "path": str(path),
                    "matched_alias": matched_alias,
                    "matched_value": candidate,
                    "extractor": extractor,
                    **(extra_details or {}),
                },
            )
        )


def append_relationship_evidence(
    *,
    evidence: list[RelationshipEvidenceFact],
    seen: set[tuple[str, str, str, str]],
    source_repo_id: str | None,
    target_repo_id: str | None,
    source_entity_id: str | None,
    target_entity_id: str | None,
    evidence_kind: str,
    relationship_type: str,
    confidence: float,
    rationale: str,
    path: Path,
    extractor: str,
    extra_details: dict[str, Any] | None = None,
) -> None:
    """Append one concrete relationship evidence fact with entity-aware ids."""

    source_identity = source_entity_id or source_repo_id
    target_identity = target_entity_id or target_repo_id
    if source_identity is None or target_identity is None:
        return
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
                "extractor": extractor,
                **(extra_details or {}),
            },
        )
    )


def match_catalog(
    candidate: str,
    catalog: Sequence[CatalogEntry],
) -> list[tuple[CatalogEntry, str]]:
    """Return unique repository matches for a raw candidate string."""

    tokens = candidate_tokens(candidate)
    matches: list[tuple[CatalogEntry, str]] = []
    for entry in catalog:
        matched_alias = next(
            (alias for alias in entry.aliases if alias in tokens), None
        )
        if matched_alias is not None:
            matches.append((entry, matched_alias))
    return matches


def candidate_tokens(candidate: str) -> set[str]:
    """Generate normalized exact-match tokens from a raw candidate string."""

    normalized = candidate.strip().lower().rstrip("/")
    if not normalized:
        return set()
    tokens = {normalized}
    if normalized.endswith(".git"):
        tokens.add(normalized[:-4])
    for part in _TOKEN_SPLIT_RE.split(normalized):
        part = part.strip().rstrip("/")
        if not part:
            continue
        tokens.add(part)
        if part.endswith(".git"):
            tokens.add(part[:-4])
        if "/" in part:
            for segment in part.split("/"):
                segment = segment.strip()
                if not segment:
                    continue
                tokens.add(segment)
                if segment.endswith(".git"):
                    tokens.add(segment[:-4])
    return tokens


def iter_yaml_files_from_content_store(
    checkout: RepositoryCheckout,
) -> list[tuple[Path, str]]:
    """Load YAML files from the Postgres content store.

    The content store is the authoritative source for indexed file content.
    This reads YAML files directly from Postgres for use by Helm, Kustomize,
    and ArgoCD evidence extractors.

    Args:
        checkout: Repository checkout record with ``logical_repo_id``.

    Returns:
        List of (synthetic_path, content) pairs for YAML files.
    """

    from ..content.state import get_postgres_content_provider

    provider = get_postgres_content_provider()
    if provider is None or not provider.enabled:
        return []

    repo_id = checkout.logical_repo_id
    yaml_files: list[tuple[Path, str]] = []

    try:
        with provider._cursor() as cursor:
            cursor.execute(
                """
                SELECT relative_path, content
                FROM content_files
                WHERE repo_id = %(repo_id)s
                  AND (
                    relative_path LIKE '%%.yaml'
                    OR relative_path LIKE '%%.yml'
                  )
                  AND content IS NOT NULL
                """,
                {"repo_id": repo_id},
            )
            for row in cursor:
                relative_path = row["relative_path"]
                content = row["content"]
                if content:
                    base = checkout.checkout_path or repo_id
                    synthetic_path = Path(base) / relative_path
                    yaml_files.append((synthetic_path, content))
    except Exception:
        return []

    return yaml_files


__all__ = [
    "CatalogEntry",
    "append_evidence_for_candidate",
    "append_relationship_evidence",
    "build_catalog",
    "checkout_path_exists",
    "is_terraform_file",
    "iter_checkout_files",
    "iter_kustomize_helm_strings",
    "iter_kustomize_image_strings",
    "iter_kustomize_resource_strings",
    "iter_terraform_files_from_content_store",
    "iter_yaml_files_from_content_store",
    "iter_yaml_strings",
    "load_yaml_documents",
    "load_yaml_documents_from_text",
    "match_catalog",
    "read_text",
]
