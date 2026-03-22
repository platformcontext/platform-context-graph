"""Workspace-backed content retrieval with graph-cache fallbacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.records import record_to_dict as _record_to_dict
from .ingest import CONTENT_ENTITY_LABELS
from ..repository_identity import (
    build_repo_access,
    canonical_repository_id,
    relative_path_from_local,
    repository_metadata,
)

__all__ = [
    "WorkspaceContentProvider",
]


class WorkspaceContentProvider:
    """Read source content directly from the server workspace and graph cache."""

    def __init__(self, database: Any) -> None:
        """Bind the provider to the current graph database.

        Args:
            database: Database dependency exposing ``get_driver()``.
        """

        self._database = database

    def get_file_content(self, *, repo_id: str, relative_path: str) -> dict[str, Any]:
        """Read one file from the server workspace.

        Args:
            repo_id: Canonical repository identifier.
            relative_path: Repo-relative file path.

        Returns:
            File content response mapping. Unavailable responses include
            ``repo_access`` only when the server cannot resolve the repository.
        """

        repository = self._resolve_repository(repo_id)
        if repository is None:
            return {
                "available": False,
                "repo_id": repo_id,
                "relative_path": relative_path,
                "content": None,
                "source_backend": "unavailable",
            }

        local_path = repository.get("local_path")
        if not local_path:
            return {
                "available": False,
                "repo_id": repository["id"],
                "relative_path": relative_path,
                "content": None,
                "source_backend": "unavailable",
                "repo_access": build_repo_access(repository),
            }

        file_path = _resolve_repo_relative_path(
            repo_root=Path(local_path),
            relative_path=relative_path,
        )
        if file_path is None or not file_path.exists() or not file_path.is_file():
            return {
                "available": False,
                "repo_id": repository["id"],
                "relative_path": relative_path,
                "content": None,
                "source_backend": "unavailable",
            }

        content = file_path.read_text(encoding="utf-8")
        return {
            "available": True,
            "repo_id": repository["id"],
            "relative_path": relative_path,
            "content": content,
            "line_count": len(content.splitlines()),
            "language": file_path.suffix.lstrip(".") or None,
            "source_backend": "workspace",
        }

    def get_file_lines(
        self,
        *,
        repo_id: str,
        relative_path: str,
        start_line: int,
        end_line: int,
    ) -> dict[str, Any]:
        """Read one line range from the server workspace.

        Args:
            repo_id: Canonical repository identifier.
            relative_path: Repo-relative file path.
            start_line: First line to include, using one-based indexing.
            end_line: Last line to include, using one-based indexing.

        Returns:
            File line-range response mapping.
        """

        file_result = self.get_file_content(
            repo_id=repo_id, relative_path=relative_path
        )
        if not file_result.get("available"):
            return {
                "available": False,
                "repo_id": repo_id,
                "relative_path": relative_path,
                "start_line": start_line,
                "end_line": end_line,
                "lines": [],
                "source_backend": file_result.get("source_backend", "unavailable"),
                "repo_access": file_result.get("repo_access"),
            }

        lines = file_result["content"].splitlines()
        slice_start = max(start_line - 1, 0)
        slice_end = max(end_line, start_line)
        return {
            "available": True,
            "repo_id": repo_id,
            "relative_path": relative_path,
            "start_line": start_line,
            "end_line": end_line,
            "lines": [
                {"line_number": index + 1, "content": line}
                for index, line in enumerate(
                    lines[slice_start:slice_end], start=slice_start
                )
            ],
            "source_backend": "workspace",
        }

    def get_entity_content(self, *, entity_id: str) -> dict[str, Any]:
        """Read one entity source snippet using the graph and workspace.

        Args:
            entity_id: Canonical content entity identifier.

        Returns:
            Entity content response mapping.
        """

        entity_row = self._resolve_entity(entity_id)
        if entity_row is None:
            return {
                "available": False,
                "entity_id": entity_id,
                "content": None,
                "source_backend": "unavailable",
            }

        repository = self._repository_for_file_path(entity_row.get("path"))
        relative_path = relative_path_from_local(
            entity_row.get("path"),
            repository.get("local_path") if repository else None,
        )

        source_cache = entity_row.get("source")
        file_path = entity_row.get("path")
        if file_path and Path(file_path).exists():
            content = _slice_file_lines(
                Path(file_path),
                start_line=int(entity_row.get("line_number") or 1),
                end_line=int(
                    entity_row.get("end_line") or entity_row.get("line_number") or 1
                ),
            )
            if content:
                return {
                    "available": True,
                    "entity_id": entity_id,
                    "repo_id": repository["id"] if repository else None,
                    "relative_path": relative_path,
                    "entity_type": entity_row["label"],
                    "entity_name": entity_row["name"],
                    "start_line": entity_row.get("line_number"),
                    "end_line": entity_row.get("end_line")
                    or entity_row.get("line_number"),
                    "language": entity_row.get("lang"),
                    "content": content,
                    "source_backend": "workspace",
                }

        if isinstance(source_cache, str) and source_cache:
            return {
                "available": True,
                "entity_id": entity_id,
                "repo_id": repository["id"] if repository else None,
                "relative_path": relative_path,
                "entity_type": entity_row["label"],
                "entity_name": entity_row["name"],
                "start_line": entity_row.get("line_number"),
                "end_line": entity_row.get("end_line") or entity_row.get("line_number"),
                "language": entity_row.get("lang"),
                "content": source_cache,
                "source_backend": "graph-cache",
            }

        response = {
            "available": False,
            "entity_id": entity_id,
            "repo_id": repository["id"] if repository else None,
            "relative_path": relative_path,
            "entity_type": entity_row["label"],
            "entity_name": entity_row["name"],
            "start_line": entity_row.get("line_number"),
            "end_line": entity_row.get("end_line") or entity_row.get("line_number"),
            "content": None,
            "source_backend": "unavailable",
        }
        if repository and not repository.get("local_path"):
            response["repo_access"] = build_repo_access(repository)
        return response

    def _resolve_repository(self, repo_id: str) -> dict[str, Any] | None:
        """Resolve one repository row from the graph.

        Args:
            repo_id: Repository identifier or slug.

        Returns:
            Normalized repository metadata row when found.
        """

        with self._database.get_driver().session() as session:
            row = _resolve_repository(session, repo_id)
        return row

    def _repository_for_file_path(self, file_path: str | None) -> dict[str, Any] | None:
        """Resolve the repository row that owns a given absolute file path.

        Args:
            file_path: Absolute file path stored on the graph node.

        Returns:
            Repository metadata row when a containing repository exists.
        """

        if not file_path:
            return None
        file_path_obj = Path(file_path)
        with self._database.get_driver().session() as session:
            rows = [_record_to_dict(record) for record in session.run(f"""
                    MATCH (r:Repository)
                    RETURN {_repository_projection()}
                    ORDER BY r.name
                    """).data()]
        candidates: list[dict[str, Any]] = []
        for row in rows:
            metadata = {**row, **_repository_metadata_from_row(row)}
            local_path = metadata.get("local_path") or metadata.get("path")
            if not local_path:
                continue
            try:
                file_path_obj.resolve().relative_to(Path(local_path).resolve())
            except ValueError:
                continue
            candidates.append(metadata)
        if not candidates:
            return None
        return max(candidates, key=lambda item: len(str(item.get("local_path") or "")))

    def _resolve_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Resolve one content-bearing graph node by its canonical content ID.

        Args:
            entity_id: Canonical content entity identifier.

        Returns:
            Normalized entity row when found.
        """

        with self._database.get_driver().session() as session:
            for label in CONTENT_ENTITY_LABELS:
                row = session.run(
                    f"""
                    MATCH (n:{label})
                    WHERE n.uid = $entity_id
                    RETURN $label as label,
                           n.name as name,
                           n.path as path,
                           n.line_number as line_number,
                           n.end_line as end_line,
                           n.lang as lang,
                           n.source as source
                    LIMIT 1
                    """,
                    entity_id=entity_id,
                    label=label,
                ).single()
                record = _record_to_dict(row)
                if record:
                    return record
        return None


def _slice_file_lines(path: Path, *, start_line: int, end_line: int) -> str:
    """Read and slice a file by one-based line range.

    Args:
        path: File to read.
        start_line: First line to include.
        end_line: Last line to include.

    Returns:
        Joined content slice, or an empty string when the range is empty.
    """

    lines = path.read_text(encoding="utf-8").splitlines()
    slice_start = max(start_line - 1, 0)
    slice_end = max(end_line, start_line)
    selected = lines[slice_start:slice_end]
    if not selected:
        return ""
    return "\n".join(selected) + "\n"


def _resolve_repo_relative_path(repo_root: Path, relative_path: str) -> Path | None:
    """Resolve a repo-relative path without allowing repository escapes.

    Args:
        repo_root: Absolute or relative repository root path.
        relative_path: Repo-relative file path supplied by the caller.

    Returns:
        Resolved path when it stays under ``repo_root``, otherwise ``None``.
    """

    if Path(relative_path).is_absolute():
        return None

    resolved_root = repo_root.resolve()
    resolved_path = (resolved_root / relative_path).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return None
    return resolved_path


def _repository_projection(alias: str = "r") -> str:
    """Return the shared repository projection used by workspace queries.

    Args:
        alias: Cypher alias for the repository node.

    Returns:
        Cypher projection fragment.
    """

    return (
        f"{alias}.id as id, "
        f"{alias}.name as name, "
        f"{alias}.path as path, "
        f"coalesce({alias}.local_path, {alias}.path) as local_path, "
        f"{alias}.remote_url as remote_url, "
        f"{alias}.repo_slug as repo_slug, "
        f"coalesce({alias}.has_remote, false) as has_remote"
    )


def _repository_metadata_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize repository metadata from a graph query row.

    Args:
        row: Repository row.

    Returns:
        Normalized repository metadata.
    """

    local_path = row.get("local_path") or row.get("path")
    return repository_metadata(
        name=row.get("name") or (Path(local_path).name if local_path else "repository"),
        local_path=local_path,
        remote_url=row.get("remote_url"),
        repo_slug=row.get("repo_slug"),
        has_remote=row.get("has_remote"),
    )


def _resolve_repository(session: Any, repo_id: str) -> dict[str, Any] | None:
    """Resolve a repository identifier against the indexed graph.

    Args:
        session: Database session used for lookup.
        repo_id: Canonical identifier, slug, path, or name fragment.

    Returns:
        Enriched repository metadata row when found.
    """

    repos = [_record_to_dict(record) for record in session.run(f"""
            MATCH (r:Repository)
            RETURN {_repository_projection()}
            ORDER BY r.name
            """).data()]

    if repo_id.startswith("repository:"):
        for repo in repos:
            metadata = _repository_metadata_from_row(repo)
            stored_id = repo.get("id") or metadata["id"]
            if stored_id == repo_id:
                return {**repo, **metadata, "id": stored_id}
        return None

    path_candidate = Path(repo_id).expanduser()
    if path_candidate.is_absolute():
        resolved_path = str(path_candidate.resolve())
        for repo in repos:
            if (
                repo.get("local_path") == resolved_path
                or repo.get("path") == resolved_path
            ):
                return {**repo, **_repository_metadata_from_row(repo)}

    lowered_identifier = repo_id.lower()
    for repo in repos:
        metadata = _repository_metadata_from_row(repo)
        candidates = [
            repo.get("name"),
            metadata.get("repo_slug"),
            metadata.get("remote_url"),
            repo.get("path"),
            metadata.get("local_path"),
            canonical_repository_id(
                remote_url=metadata.get("remote_url"),
                local_path=metadata.get("local_path"),
            ),
        ]
        if any(
            candidate and lowered_identifier in str(candidate).lower()
            for candidate in candidates
        ):
            return {**repo, **metadata, "id": repo.get("id") or metadata["id"]}
    return None
