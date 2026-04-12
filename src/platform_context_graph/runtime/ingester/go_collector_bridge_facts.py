"""Fact-shaping helpers for the Go collector compatibility bridge."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from platform_context_graph.facts.models.base import stable_fact_id


def bridge_scope(
    *,
    repo_id: str,
    repo_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build the durable ingestion scope for one repository."""

    metadata = {
        "repo_id": repo_id,
        "repo_name": str(repo_metadata["name"]),
        "source_key": repo_id,
    }
    repo_slug = repo_metadata.get("repo_slug")
    if repo_slug:
        metadata["repo_slug"] = str(repo_slug)
    remote_url = repo_metadata.get("remote_url")
    if remote_url:
        metadata["remote_url"] = str(remote_url)
    local_path = repo_metadata.get("local_path")
    if local_path:
        metadata["local_path"] = str(local_path)

    return {
        "scope_id": f"git-repository-scope:{repo_id}",
        "source_system": "git",
        "scope_kind": "repository",
        "parent_scope_id": "",
        "collector_kind": "git",
        "partition_key": repo_id,
        "metadata": metadata,
    }


def bridge_generation(
    *,
    scope_id: str,
    repo_path: Path,
    source_run_id: str,
    observed_at: datetime,
    source_snapshot_id_fn: Callable[..., str],
) -> dict[str, str]:
    """Build the durable source generation for one repository snapshot."""

    return {
        "generation_id": source_snapshot_id_fn(
            source_run_id=source_run_id,
            repo_path=repo_path,
        ),
        "scope_id": scope_id,
        "observed_at": observed_at.isoformat(),
        "ingested_at": observed_at.isoformat(),
        "status": "pending",
        "trigger_kind": "snapshot",
        "freshness_hint": "snapshot",
    }


def repository_fact(
    *,
    repo_path: Path,
    repo_id: str,
    repo_metadata: dict[str, Any],
    scope_id: str,
    generation_id: str,
    observed_at: datetime,
    parsed_file_count: int,
) -> dict[str, Any]:
    """Build the repository graph fact."""

    payload = {
        "graph_id": repo_id,
        "graph_kind": "repository",
        "name": str(repo_metadata["name"]),
        "repo_id": repo_id,
        "parsed_file_count": str(parsed_file_count),
    }
    repo_slug = repo_metadata.get("repo_slug")
    if repo_slug:
        payload["repo_slug"] = str(repo_slug)
    remote_url = repo_metadata.get("remote_url")
    if remote_url:
        payload["remote_url"] = str(remote_url)
    local_path = repo_metadata.get("local_path")
    if local_path:
        payload["local_path"] = str(local_path)

    return _fact_record(
        fact_kind="repository",
        scope_id=scope_id,
        generation_id=generation_id,
        observed_at=observed_at,
        fact_key=f"repository:{repo_id}",
        payload=payload,
        source_uri=str(repo_path.resolve()),
    )


def file_fact(
    *,
    repo_path: Path,
    repo_id: str,
    file_path: Path,
    language: str | None,
    scope_id: str,
    generation_id: str,
    observed_at: datetime,
) -> dict[str, Any]:
    """Build the file graph fact."""

    relative_path = _relative_path(repo_path, file_path)
    payload = {
        "graph_id": f"{repo_id}:{relative_path}",
        "graph_kind": "file",
        "repo_id": repo_id,
        "relative_path": relative_path,
    }
    if language:
        payload["language"] = language

    return _fact_record(
        fact_kind="file",
        scope_id=scope_id,
        generation_id=generation_id,
        observed_at=observed_at,
        fact_key=f"file:{repo_id}:{relative_path}",
        payload=payload,
        source_uri=str(file_path.resolve()),
    )


def content_fact(
    *,
    repo_path: Path,
    repo_id: str,
    file_path: Path,
    language: str | None,
    scope_id: str,
    generation_id: str,
    observed_at: datetime,
) -> dict[str, Any]:
    """Build the file-content fact."""

    relative_path = _relative_path(repo_path, file_path)
    payload = {
        "content_path": relative_path,
        "content_body": file_path.read_text(encoding="utf-8"),
        "content_digest": _content_digest(file_path),
        "repo_id": repo_id,
    }
    if language:
        payload["language"] = language

    return _fact_record(
        fact_kind="content",
        scope_id=scope_id,
        generation_id=generation_id,
        observed_at=observed_at,
        fact_key=f"content:{repo_id}:{relative_path}",
        payload=payload,
        source_uri=str(file_path.resolve()),
    )


def workload_identity_fact(
    *,
    repo_path: Path,
    repo_id: str,
    scope_id: str,
    generation_id: str,
    observed_at: datetime,
) -> dict[str, Any]:
    """Build the shared workload-identity follow-up fact."""

    return _fact_record(
        fact_kind="shared_followup",
        scope_id=scope_id,
        generation_id=generation_id,
        observed_at=observed_at,
        fact_key=f"shared_followup:{repo_id}:workload_identity",
        payload={
            "reducer_domain": "workload_identity",
            "entity_key": f"workload:{repo_path.name}",
            "reason": (
                "repository snapshot emitted shared workload identity follow-up"
            ),
            "repo_id": repo_id,
        },
        source_uri=str(repo_path.resolve()),
    )


def _content_digest(path: Path) -> str:
    """Return the canonical SHA-1 content digest for one file."""

    return hashlib.sha1(path.read_bytes()).hexdigest()


def _relative_path(repo_path: Path, file_path: Path) -> str:
    """Return a repository-relative POSIX path."""

    return file_path.resolve().relative_to(repo_path.resolve()).as_posix()


def _fact_record(
    *,
    fact_kind: str,
    scope_id: str,
    generation_id: str,
    observed_at: datetime,
    fact_key: str,
    payload: dict[str, str],
    source_uri: str,
) -> dict[str, Any]:
    """Build one Go-shaped fact envelope JSON record."""

    return {
        "fact_id": stable_fact_id(
            fact_type="GoCollectorBridgeFact",
            identity={
                "scope_id": scope_id,
                "generation_id": generation_id,
                "fact_kind": fact_kind,
                "fact_key": fact_key,
            },
        ),
        "scope_id": scope_id,
        "generation_id": generation_id,
        "fact_kind": fact_kind,
        "stable_fact_key": fact_key,
        "observed_at": observed_at.isoformat(),
        "payload": payload,
        "is_tombstone": False,
        "source_ref": {
            "source_system": "git",
            "scope_id": scope_id,
            "generation_id": generation_id,
            "fact_key": fact_key,
            "source_uri": source_uri,
            "source_record_id": fact_key,
        },
    }
