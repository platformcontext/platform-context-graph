"""Helpers for dual-writing indexed source content into the content store."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..repository_identity import (
    git_remote_for_path,
    relative_path_from_local,
    repository_metadata,
)
from ..tools.languages.templated_detection import infer_content_metadata
from ..utils.source_text import read_source_text
from .identity import canonical_content_entity_id
from .models import ContentEntityEntry, ContentFileEntry

__all__ = [
    "CONTENT_ENTITY_BUCKETS",
    "CONTENT_ENTITY_LABELS",
    "prepare_content_entries",
    "repository_metadata_from_row",
]

CONTENT_ENTITY_BUCKETS: tuple[tuple[str, str], ...] = (
    ("functions", "Function"),
    ("classes", "Class"),
    ("variables", "Variable"),
    ("traits", "Trait"),
    ("interfaces", "Interface"),
    ("macros", "Macro"),
    ("structs", "Struct"),
    ("enums", "Enum"),
    ("unions", "Union"),
    ("annotations", "Annotation"),
    ("records", "Record"),
    ("properties", "Property"),
    ("k8s_resources", "K8sResource"),
    ("argocd_applications", "ArgoCDApplication"),
    ("argocd_applicationsets", "ArgoCDApplicationSet"),
    ("crossplane_xrds", "CrossplaneXRD"),
    ("crossplane_compositions", "CrossplaneComposition"),
    ("crossplane_claims", "CrossplaneClaim"),
    ("kustomize_overlays", "KustomizeOverlay"),
    ("helm_charts", "HelmChart"),
    ("helm_values", "HelmValues"),
    ("terraform_resources", "TerraformResource"),
    ("terraform_variables", "TerraformVariable"),
    ("terraform_outputs", "TerraformOutput"),
    ("terraform_modules", "TerraformModule"),
    ("terraform_data_sources", "TerraformDataSource"),
    ("terraform_providers", "TerraformProvider"),
    ("terraform_locals", "TerraformLocal"),
    ("terragrunt_configs", "TerragruntConfig"),
    ("cloudformation_resources", "CloudFormationResource"),
    ("cloudformation_parameters", "CloudFormationParameter"),
    ("cloudformation_outputs", "CloudFormationOutput"),
)
CONTENT_ENTITY_LABELS = frozenset(label for _, label in CONTENT_ENTITY_BUCKETS)

_SOURCE_FIELD_CONTAINS_CODE = {
    "Annotation",
    "Class",
    "Enum",
    "Function",
    "Interface",
    "Macro",
    "Property",
    "Record",
    "Struct",
    "Trait",
    "Union",
    "Variable",
}
_TRAILING_NEWLINE_LABELS = _SOURCE_FIELD_CONTAINS_CODE | {
    "ArgoCDApplication",
    "ArgoCDApplicationSet",
    "CrossplaneClaim",
    "CrossplaneComposition",
    "CrossplaneXRD",
    "HelmChart",
    "HelmValues",
    "K8sResource",
    "KustomizeOverlay",
    "CloudFormationOutput",
    "CloudFormationParameter",
    "CloudFormationResource",
    "TerraformDataSource",
    "TerraformLocal",
    "TerraformModule",
    "TerraformOutput",
    "TerraformProvider",
    "TerraformResource",
    "TerraformVariable",
    "TerragruntConfig",
}


def repository_metadata_from_row(
    *, row: dict[str, Any] | None, repo_path: Path
) -> dict[str, Any]:
    """Normalize repository metadata from a graph row or on-disk fallback.

    Args:
        row: Repository row returned from the graph, if one exists.
        repo_path: Local repository root containing the indexed file.

    Returns:
        Canonical repository metadata using remote-first identity.
    """

    if row:
        normalized = repository_metadata(
            name=row.get("name") or repo_path.name,
            local_path=row.get("local_path") or row.get("path") or repo_path,
            remote_url=row.get("remote_url"),
            repo_slug=row.get("repo_slug"),
            has_remote=row.get("has_remote"),
        )
        if row.get("id"):
            normalized["id"] = row["id"]
        return normalized

    return repository_metadata(
        name=repo_path.name,
        local_path=repo_path,
        remote_url=git_remote_for_path(repo_path),
    )


def prepare_content_entries(
    *,
    file_data: dict[str, Any],
    repository: dict[str, Any],
) -> tuple[ContentFileEntry | None, list[ContentEntityEntry]]:
    """Build content-store rows for one indexed file and its parsed entities.

    Args:
        file_data: Parsed file payload emitted by the language parser.
        repository: Canonical repository metadata for the file's owning repo.

    Returns:
        Tuple of the file-content row, when the file can be read, and the list
        of entity-content rows derived from the file payload.
    """

    file_path = Path(file_data["path"])
    repo_local_path = repository.get("local_path")
    resolved_file_path = _resolve_repo_contained_path(file_path, repo_local_path)
    if resolved_file_path is None:
        return None, []

    relative_path = _portable_relative_path(file_path, repo_local_path)
    file_content = _read_text(resolved_file_path)
    file_lines = file_content.splitlines() if file_content is not None else []
    metadata = infer_content_metadata(
        relative_path=Path(relative_path),
        content=file_content or "",
    )

    entities = _build_entity_entries(
        file_data=file_data,
        repository=repository,
        relative_path=relative_path,
        file_lines=file_lines,
        metadata=metadata,
    )

    file_entry = None
    if file_content is not None:
        file_entry = ContentFileEntry(
            repo_id=repository["id"],
            relative_path=relative_path,
            content=file_content,
            language=file_data.get("lang"),
            artifact_type=metadata.artifact_type,
            template_dialect=metadata.template_dialect,
            iac_relevant=metadata.iac_relevant,
            commit_sha=_git_commit_sha(repo_local_path),
        )

    return file_entry, entities


def _resolve_repo_contained_path(
    file_path: Path, repo_local_path: str | None
) -> Path | None:
    """Resolve a file path only when it stays inside the repository root."""

    resolved_file_path = file_path.resolve()
    if repo_local_path is None:
        return resolved_file_path

    repo_root = Path(repo_local_path).expanduser().resolve()
    try:
        resolved_file_path.relative_to(repo_root)
    except ValueError:
        return None
    return resolved_file_path


def _build_entity_entries(
    *,
    file_data: dict[str, Any],
    repository: dict[str, Any],
    relative_path: str,
    file_lines: list[str],
    metadata: Any,
) -> list[ContentEntityEntry]:
    """Build content-store entity rows and attach canonical UIDs to items."""

    indexed_items: list[tuple[str, dict[str, Any]]] = []
    for bucket_name, label in CONTENT_ENTITY_BUCKETS:
        for item in file_data.get(bucket_name, []):
            indexed_items.append((label, item))

    indexed_items.sort(
        key=lambda entry: (
            _line_number(entry[1]),
            entry[0],
            str(entry[1].get("name", "")),
        )
    )

    entries: list[ContentEntityEntry] = []
    for index, (label, item) in enumerate(indexed_items):
        line_number = _line_number(item)
        end_line = _end_line(
            item=item,
            next_line=_next_line_number(indexed_items, index),
            total_lines=len(file_lines),
        )
        entity_id = canonical_content_entity_id(
            repo_id=repository["id"],
            relative_path=relative_path,
            entity_type=label,
            entity_name=str(item.get("name", "")),
            line_number=line_number,
        )
        item["uid"] = entity_id
        source_cache = _source_cache(
            label=label,
            item=item,
            file_lines=file_lines,
            start_line=line_number,
            end_line=end_line,
        )
        entries.append(
            ContentEntityEntry(
                entity_id=entity_id,
                repo_id=repository["id"],
                relative_path=relative_path,
                entity_type=label,
                entity_name=str(item.get("name", "")),
                start_line=line_number,
                end_line=end_line,
                start_byte=item.get("start_byte"),
                end_byte=item.get("end_byte"),
                language=item.get("lang") or file_data.get("lang"),
                artifact_type=metadata.artifact_type,
                template_dialect=metadata.template_dialect,
                iac_relevant=metadata.iac_relevant,
                source_cache=source_cache,
            )
        )

    return entries


def _portable_relative_path(file_path: Path, repo_local_path: str | None) -> str:
    """Return a repo-relative path suitable for portable API responses."""

    if file_path.is_absolute() and repo_local_path is not None:
        try:
            return (
                file_path.expanduser()
                .relative_to(Path(repo_local_path).expanduser().resolve())
                .as_posix()
            )
        except ValueError:
            pass

    relative_path = relative_path_from_local(file_path, repo_local_path)
    if relative_path is None:
        return file_path.name
    relative = Path(relative_path)
    if relative.is_absolute():
        return file_path.name
    return relative.as_posix()


def _read_text(file_path: Path) -> str | None:
    """Read a source file for content-store ingestion with legacy fallbacks."""

    try:
        return read_source_text(file_path)
    except (OSError, ValueError):
        return None


def _line_number(item: dict[str, Any]) -> int:
    """Return a safe one-based line number for one parsed entity item."""

    raw_line = item.get("line_number")
    if isinstance(raw_line, int) and raw_line >= 1:
        return raw_line
    return 1


def _next_line_number(
    indexed_items: list[tuple[str, dict[str, Any]]], index: int
) -> int | None:
    """Return the next entity start line for slice-derivation heuristics."""

    for _label, item in indexed_items[index + 1 :]:
        line_number = _line_number(item)
        if line_number >= _line_number(indexed_items[index][1]):
            return line_number
    return None


def _end_line(
    *,
    item: dict[str, Any],
    next_line: int | None,
    total_lines: int,
) -> int:
    """Return the best end line for one entity content slice."""

    raw_end_line = item.get("end_line")
    if isinstance(raw_end_line, int) and raw_end_line >= _line_number(item):
        return raw_end_line
    if next_line is not None:
        return max(_line_number(item), next_line - 1)
    if total_lines:
        return min(total_lines, _line_number(item) + 24)
    return _line_number(item)


def _source_cache(
    *,
    label: str,
    item: dict[str, Any],
    file_lines: list[str],
    start_line: int,
    end_line: int,
) -> str:
    """Return the best available source snippet for one content entity."""

    explicit_source = item.get("source")
    if (
        label in _SOURCE_FIELD_CONTAINS_CODE
        and isinstance(explicit_source, str)
        and explicit_source.strip()
    ):
        return _with_trailing_newline(explicit_source, label=label)

    if file_lines:
        selected = file_lines[max(start_line - 1, 0) : max(end_line, start_line)]
        if selected:
            return _with_trailing_newline("\n".join(selected), label=label)

    if isinstance(explicit_source, str):
        return explicit_source
    return ""


def _with_trailing_newline(content: str, *, label: str) -> str:
    """Normalize multi-line snippets so downstream rendering is consistent."""

    if label not in _TRAILING_NEWLINE_LABELS:
        return content
    return content if not content or content.endswith("\n") else f"{content}\n"


@lru_cache(maxsize=128)
def _git_commit_sha(local_path: str | None) -> str | None:
    """Return the current git commit for a repository root, if available."""

    if not local_path:
        return None

    result = subprocess.run(
        ["git", "-C", str(Path(local_path).resolve()), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return None
    commit_sha = result.stdout.strip()
    return commit_sha or None
