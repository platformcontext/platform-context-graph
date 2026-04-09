"""Support helpers for batched runtime dependency materialization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..shared_projection import build_repo_dependency_intent_rows
from ..shared_projection import build_workload_dependency_intent_rows
from ..shared_projection import dependency_shared_projection_worker_enabled
from ..shared_projection import emit_dependency_intents
from ..shared_projection import existing_repo_dependency_rows
from ..shared_projection import existing_workload_dependency_rows
from ..shared_projection import shared_dependency_projection_metrics
from .batches import write_repo_dependency_rows
from .batches import write_workload_dependency_rows
from ...parsers.languages.runtime_dependencies import (
    extract_runtime_service_dependencies,
)


def _read_file_contents_store_first(
    file_rows: list[dict[str, object]],
) -> dict[tuple[str, str], str]:
    """Read file content from the content store first, filesystem second."""

    from ...content.state import get_postgres_content_provider

    requested_files = [
        {
            "repo_id": str(row.get("repo_id") or ""),
            "relative_path": str(row.get("relative_path") or ""),
            "filesystem_path": str(row.get("path") or ""),
        }
        for row in file_rows
        if str(row.get("repo_id") or "").strip()
        and str(row.get("relative_path") or "").strip()
    ]
    if not requested_files:
        return {}

    provider = get_postgres_content_provider()
    contents_by_file: dict[tuple[str, str], str] = {}
    if provider is not None and provider.enabled:
        try:
            contents_by_file.update(
                provider.get_file_contents_batch(
                    repo_files=[
                        {
                            "repo_id": row["repo_id"],
                            "relative_path": row["relative_path"],
                        }
                        for row in requested_files
                    ]
                )
            )
        except Exception:
            pass

    for row in requested_files:
        cache_key = (row["repo_id"], row["relative_path"])
        if cache_key in contents_by_file:
            continue
        path = Path(row["filesystem_path"]).expanduser()
        if not path.is_file():
            continue
        try:
            contents_by_file[cache_key] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return contents_by_file


def _load_runtime_dependency_targets(
    session: Any,
    *,
    repo_descriptors: list[dict[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Collect dependency edges for the targeted workloads."""

    if not repo_descriptors:
        return [], []

    file_rows = session.run(
        """
        UNWIND $rows AS row
        MATCH (repo:Repository {id: row.repo_id})-[:REPO_CONTAINS]->(f:File)
        WHERE f.name IN [row.typescript_entrypoint, row.javascript_entrypoint]
        RETURN f.path as path,
               row.repo_id as repo_id,
               row.repo_name as repo_name,
               f.relative_path as relative_path
        ORDER BY repo.name, f.relative_path
        """,
        rows=[
            {
                "javascript_entrypoint": f"{row['repo_name']}.js",
                "repo_id": row["repo_id"],
                "repo_name": row["repo_name"],
                "typescript_entrypoint": f"{row['repo_name']}.ts",
            }
            for row in repo_descriptors
        ],
    ).data()

    dependencies_by_repo: dict[str, list[str]] = {}
    descriptors_by_repo_id = {row["repo_id"]: row for row in repo_descriptors}
    contents_by_file = _read_file_contents_store_first(file_rows)
    for row in file_rows:
        repo_id = str(row.get("repo_id") or "")
        descriptor = descriptors_by_repo_id.get(repo_id)
        if descriptor is None:
            continue
        content = contents_by_file.get(
            (
                repo_id,
                str(row.get("relative_path") or ""),
            )
        )
        if content is None:
            continue
        dependencies = dependencies_by_repo.setdefault(repo_id, [])
        for dependency_name in extract_runtime_service_dependencies(
            content,
            workload_name=descriptor["repo_name"],
        ):
            if dependency_name not in dependencies:
                dependencies.append(dependency_name)

    dependency_names = sorted(
        {
            dependency_name
            for dependency_list in dependencies_by_repo.values()
            for dependency_name in dependency_list
        }
    )
    if not dependency_names:
        return [], []

    target_rows = session.run(
        """
        MATCH (target_repo:Repository)
        WHERE target_repo.name IN $dependency_names
        RETURN target_repo.id as repo_id, target_repo.name as repo_name
        """,
        dependency_names=dependency_names,
    ).data()
    target_repo_ids = {
        str(row.get("repo_name") or ""): str(row.get("repo_id") or "")
        for row in target_rows
        if row.get("repo_id") and row.get("repo_name")
    }

    repo_dependency_rows: list[dict[str, object]] = []
    workload_dependency_rows: list[dict[str, object]] = []
    seen_repo_edges: set[tuple[str, str]] = set()
    seen_workload_edges: set[tuple[str, str]] = set()
    for repo_id, dependency_names_for_repo in dependencies_by_repo.items():
        descriptor = descriptors_by_repo_id[repo_id]
        for dependency_name in dependency_names_for_repo:
            target_repo_id = target_repo_ids.get(dependency_name)
            if not target_repo_id:
                continue
            repo_edge = (repo_id, target_repo_id)
            if repo_edge not in seen_repo_edges:
                seen_repo_edges.add(repo_edge)
                repo_dependency_rows.append(
                    {
                        "dependency_name": dependency_name,
                        "repo_id": repo_id,
                        "target_repo_id": target_repo_id,
                    }
                )
            workload_edge = (descriptor["workload_id"], target_repo_id)
            if workload_edge in seen_workload_edges:
                continue
            seen_workload_edges.add(workload_edge)
            workload_dependency_rows.append(
                {
                    "dependency_name": dependency_name,
                    "repo_id": repo_id,
                    "target_repo_id": target_repo_id,
                    "target_workload_id": f"workload:{dependency_name}",
                    "workload_id": descriptor["workload_id"],
                }
            )

    return repo_dependency_rows, workload_dependency_rows


def materialize_runtime_dependencies(
    session: Any,
    *,
    repo_descriptors: list[dict[str, str]],
    evidence_source: str,
    progress_callback: Any | None = None,
    projection_context_by_repo_id: dict[str, dict[str, str]] | None = None,
    shared_projection_intent_store: Any | None = None,
    load_runtime_dependency_targets_fn: Any | None = None,
) -> dict[str, int]:
    """Create repo and workload dependency edges from runtime service lists."""

    if load_runtime_dependency_targets_fn is None:
        load_runtime_dependency_targets_fn = _load_runtime_dependency_targets
    repo_dependency_rows, workload_dependency_rows = load_runtime_dependency_targets_fn(
        session,
        repo_descriptors=repo_descriptors,
    )
    worker_cutover = (
        dependency_shared_projection_worker_enabled()
        and shared_projection_intent_store is not None
        and projection_context_by_repo_id
    )
    if worker_cutover:
        repo_ids = sorted(
            {
                str(row["repo_id"])
                for row in repo_descriptors
                if str(row.get("repo_id") or "").strip()
            }
        )
        intent_rows = build_repo_dependency_intent_rows(
            repo_dependency_rows=repo_dependency_rows,
            existing_rows=existing_repo_dependency_rows(
                session,
                repo_ids=repo_ids,
                evidence_source=evidence_source,
            ),
            projection_context_by_repo_id=projection_context_by_repo_id,
        ) + build_workload_dependency_intent_rows(
            workload_dependency_rows=workload_dependency_rows,
            existing_rows=existing_workload_dependency_rows(
                session,
                repo_ids=repo_ids,
                evidence_source=evidence_source,
            ),
            projection_context_by_repo_id=projection_context_by_repo_id,
        )
        if intent_rows:
            shared_projection_intent_store.upsert_intents(intent_rows)
        return {
            "repo_dependency_edges_projected": 0,
            "workload_dependency_edges_projected": 0,
            "write_chunk_count": 0,
            "shared_projection": shared_dependency_projection_metrics(
                intent_rows=intent_rows,
                projection_context_by_repo_id=projection_context_by_repo_id,
            ),
        }

    emit_dependency_intents(
        shared_projection_intent_store=shared_projection_intent_store,
        repo_dependency_rows=repo_dependency_rows,
        workload_dependency_rows=workload_dependency_rows,
        projection_context_by_repo_id=projection_context_by_repo_id,
    )
    repo_write_metrics = write_repo_dependency_rows(
        session,
        repo_dependency_rows,
        evidence_source=evidence_source,
        progress_callback=progress_callback,
    )
    workload_write_metrics = write_workload_dependency_rows(
        session,
        workload_dependency_rows,
        evidence_source=evidence_source,
        progress_callback=progress_callback,
    )
    return {
        "repo_dependency_edges_projected": len(repo_dependency_rows),
        "workload_dependency_edges_projected": len(workload_dependency_rows),
        "write_chunk_count": (
            repo_write_metrics["write_chunk_count"]
            + workload_write_metrics["write_chunk_count"]
        ),
    }


__all__ = ["materialize_runtime_dependencies"]
