"""Durable repo-batch indexing coordinator with checkpointed resume support."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from platform_context_graph.observability import get_observability
from platform_context_graph.paths import get_app_home
from platform_context_graph.repository_identity import git_remote_for_path, repository_metadata
from platform_context_graph.tools.graph_builder_indexing import (
    apply_ignore_spec,
    discover_git_repositories,
    discover_index_files,
    find_pcgignore,
    finalize_index_batch,
    merge_import_maps,
    parse_repository_snapshot_async,
    resolve_repository_file_sets,
)
from platform_context_graph.utils.debug_log import error_logger, info_logger, warning_logger

RUNS_DIRNAME = "index-runs"
RUN_STATE_FILENAME = "run.json"
SNAPSHOT_DIRNAME = "snapshots"
ACTIVE_REPO_STATES = {"pending", "running", "parsed", "commit_incomplete", "failed"}
TERMINAL_REPO_STATES = {"completed", "skipped"}


@dataclass(slots=True)
class RepositoryRunState:
    """Checkpoint state for one repository inside a run."""

    repo_path: str
    status: str = "pending"
    file_count: int = 0
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class IndexRunState:
    """Durable checkpoint state for one repo-batch indexing run."""

    run_id: str
    root_path: str
    family: str
    source: str
    discovery_signature: str
    is_dependency: bool
    status: str
    finalization_status: str
    created_at: str
    updated_at: str
    last_error: str | None = None
    repositories: dict[str, RepositoryRunState] = field(default_factory=dict)

    def pending_repositories(self) -> int:
        """Return the number of repositories still requiring work."""

        return sum(
            1
            for state in self.repositories.values()
            if state.status not in TERMINAL_REPO_STATES
        )

    def completed_repositories(self) -> int:
        """Return the number of repositories completed successfully."""

        return sum(
            1 for state in self.repositories.values() if state.status == "completed"
        )

    def failed_repositories(self) -> int:
        """Return the number of repositories left in a failed-like state."""

        return sum(
            1
            for state in self.repositories.values()
            if state.status in {"failed", "commit_incomplete"}
        )


@dataclass(slots=True)
class IndexExecutionResult:
    """Outcome summary for one coordinated index run."""

    run_id: str
    root_path: Path
    repository_count: int
    completed_repositories: int
    failed_repositories: int
    resumed_repositories: int
    skipped_repositories: int
    finalization_status: str
    status: str


@dataclass(slots=True)
class RepositorySnapshot:
    """Durable staged parse output for one repository."""

    repo_path: str
    file_count: int
    imports_map: dict[str, list[str]]
    file_data: list[dict[str, Any]]


def _utc_now() -> str:
    """Return the current UTC time in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()


def _runs_root() -> Path:
    """Return the root directory used for durable index checkpoints."""

    root = get_app_home() / RUNS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalize_paths(paths: Sequence[Path]) -> list[Path]:
    """Return unique, sorted, resolved repository paths."""

    normalized = {path.resolve() for path in paths}
    return sorted(normalized)


def _signature_for_repositories(repo_paths: Sequence[Path]) -> str:
    """Return a stable discovery signature for the selected repositories."""

    digest = sha256()
    for repo_path in _normalize_paths(repo_paths):
        digest.update(str(repo_path).encode("utf-8"))
    return digest.hexdigest()


def _run_id_for(
    *,
    root_path: Path,
    family: str,
    source: str,
    discovery_signature: str,
    is_dependency: bool,
) -> str:
    """Return the stable identifier for a run/checkpoint directory."""

    digest = sha256()
    digest.update(str(root_path.resolve()).encode("utf-8"))
    digest.update(family.encode("utf-8"))
    digest.update(source.encode("utf-8"))
    digest.update(discovery_signature.encode("utf-8"))
    digest.update(str(int(is_dependency)).encode("utf-8"))
    return digest.hexdigest()[:16]


def _run_dir(run_id: str) -> Path:
    """Return the on-disk directory for a checkpointed run."""

    return _runs_root() / run_id


def _run_state_path(run_id: str) -> Path:
    """Return the JSON checkpoint path for one run."""

    return _run_dir(run_id) / RUN_STATE_FILENAME


def _snapshot_dir(run_id: str) -> Path:
    """Return the directory holding staged per-repo snapshots."""

    path = _run_dir(run_id) / SNAPSHOT_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _snapshot_path(run_id: str, repo_path: Path) -> Path:
    """Return the staged snapshot file path for one repository."""

    repo_key = sha256(str(repo_path.resolve()).encode("utf-8")).hexdigest()[:16]
    return _snapshot_dir(run_id) / f"{repo_key}.json"


def _serialize_run_state(state: IndexRunState) -> dict[str, Any]:
    """Convert a run checkpoint into JSON-serializable data."""

    payload = asdict(state)
    payload["repositories"] = {
        repo_path: asdict(repo_state)
        for repo_path, repo_state in state.repositories.items()
    }
    return payload


def _deserialize_run_state(payload: dict[str, Any]) -> IndexRunState:
    """Return an in-memory checkpoint from persisted JSON."""

    repositories = {
        repo_path: RepositoryRunState(**repo_state)
        for repo_path, repo_state in payload.get("repositories", {}).items()
    }
    return IndexRunState(
        run_id=payload["run_id"],
        root_path=payload["root_path"],
        family=payload["family"],
        source=payload["source"],
        discovery_signature=payload["discovery_signature"],
        is_dependency=bool(payload["is_dependency"]),
        status=payload["status"],
        finalization_status=payload["finalization_status"],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        last_error=payload.get("last_error"),
        repositories=repositories,
    )


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically using temp-file-plus-rename semantics."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _load_run_state(path: Path) -> IndexRunState | None:
    """Load a checkpoint JSON file when it exists."""

    if not path.exists():
        return None
    return _deserialize_run_state(json.loads(path.read_text(encoding="utf-8")))


def _archive_run(run_id: str, *, reason: str) -> None:
    """Archive a checkpoint directory in place."""

    run_dir = _run_dir(run_id)
    if not run_dir.exists():
        return
    archived_path = run_dir.with_name(f"{run_dir.name}.archived-{int(time.time())}")
    shutil.move(str(run_dir), str(archived_path))
    state_path = archived_path / RUN_STATE_FILENAME
    state = _load_run_state(state_path)
    if state is None:
        return
    state.status = "archived"
    state.updated_at = _utc_now()
    state.last_error = reason
    _write_json_atomic(state_path, _serialize_run_state(state))


def _matching_run_states(root_path: Path) -> list[IndexRunState]:
    """Return all persisted runs matching the requested root path."""

    matches: list[IndexRunState] = []
    for state_path in _runs_root().glob(f"*/{RUN_STATE_FILENAME}"):
        state = _load_run_state(state_path)
        if state is None:
            continue
        if Path(state.root_path).resolve() == root_path.resolve():
            matches.append(state)
    matches.sort(key=lambda item: item.updated_at, reverse=True)
    return matches


def _persist_run_state(state: IndexRunState) -> None:
    """Persist the current checkpoint state to disk."""

    state.updated_at = _utc_now()
    _write_json_atomic(_run_state_path(state.run_id), _serialize_run_state(state))


def _load_or_create_run(
    *,
    root_path: Path,
    family: str,
    source: str,
    repo_paths: Sequence[Path],
    is_dependency: bool,
) -> tuple[IndexRunState, bool]:
    """Load a resumable run when possible or create a fresh checkpoint."""

    discovery_signature = _signature_for_repositories(repo_paths)
    existing_runs = [
        run
        for run in _matching_run_states(root_path)
        if run.family == family and run.source == source and run.is_dependency == is_dependency
    ]
    for run in existing_runs:
        if run.discovery_signature == discovery_signature and run.status in {
            "running",
            "partial_failure",
            "failed",
        }:
            return run, True
        if run.status in {"running", "partial_failure", "failed"}:
            _archive_run(
                run.run_id,
                reason="Discovery signature changed; archived unfinished checkpoint",
            )

    run_id = _run_id_for(
        root_path=root_path,
        family=family,
        source=source,
        discovery_signature=discovery_signature,
        is_dependency=is_dependency,
    )
    if _run_dir(run_id).exists():
        _archive_run(run_id, reason="Fresh run replaced prior checkpoint")

    created_at = _utc_now()
    state = IndexRunState(
        run_id=run_id,
        root_path=str(root_path.resolve()),
        family=family,
        source=source,
        discovery_signature=discovery_signature,
        is_dependency=is_dependency,
        status="running",
        finalization_status="pending",
        created_at=created_at,
        updated_at=created_at,
        repositories={
            str(repo_path.resolve()): RepositoryRunState(repo_path=str(repo_path.resolve()))
            for repo_path in _normalize_paths(repo_paths)
        },
    )
    _persist_run_state(state)
    return state, False


def _save_snapshot(run_id: str, snapshot: RepositorySnapshot) -> None:
    """Persist one parsed repository snapshot to disk."""

    _write_json_atomic(_snapshot_path(run_id, Path(snapshot.repo_path)), asdict(snapshot))


def _load_snapshot(run_id: str, repo_path: Path) -> RepositorySnapshot | None:
    """Load one staged snapshot when present."""

    path = _snapshot_path(run_id, repo_path)
    if not path.exists():
        return None
    return RepositorySnapshot(**json.loads(path.read_text(encoding="utf-8")))


def _delete_snapshots(run_id: str) -> None:
    """Remove staged repository snapshots after finalization succeeds."""

    shutil.rmtree(_snapshot_dir(run_id), ignore_errors=True)


def _record_checkpoint_metric(
    *,
    component: str,
    mode: str,
    source: str,
    operation: str,
    status: str,
) -> None:
    """Emit one checkpoint operation metric."""

    get_observability().record_index_checkpoint(
        component=component,
        mode=mode,
        source=source,
        operation=operation,
        status=status,
    )


def _update_pending_repository_gauge(
    *,
    component: str,
    mode: str,
    source: str,
    pending_count: int,
) -> None:
    """Publish the current pending repository checkpoint count."""

    get_observability().set_index_checkpoint_pending_repositories(
        component=component,
        mode=mode,
        source=source,
        pending_count=pending_count,
    )


def _commit_repository_snapshot(
    builder: Any,
    snapshot: RepositorySnapshot,
    *,
    is_dependency: bool,
) -> None:
    """Replace one repository's persisted graph/content state from a snapshot."""

    repo_path = Path(snapshot.repo_path).resolve()
    metadata = repository_metadata(
        name=repo_path.name,
        local_path=str(repo_path),
        remote_url=git_remote_for_path(repo_path),
    )
    content_provider = getattr(builder, "_content_provider", None)
    if content_provider is None:
        from platform_context_graph.content.state import get_postgres_content_provider

        content_provider = get_postgres_content_provider()
        builder._content_provider = content_provider

    if content_provider is not None and content_provider.enabled:
        content_provider.delete_repository_content(metadata["id"])

    try:
        builder.delete_repository_from_graph(str(repo_path))
    except Exception:
        pass

    builder.add_repository_to_graph(repo_path, is_dependency=is_dependency)
    for file_data in snapshot.file_data:
        builder.add_file_to_graph(file_data, repo_path.name, snapshot.imports_map)


async def execute_index_run(
    builder: Any,
    root_path: Path,
    *,
    is_dependency: bool = False,
    job_id: str | None = None,
    selected_repositories: Sequence[Path] | None = None,
    family: str,
    source: str,
    force: bool,
    component: str,
    asyncio_module: Any,
    datetime_cls: Any,
    info_logger_fn: Any,
    warning_logger_fn: Any,
    error_logger_fn: Any,
    job_status_enum: Any,
    pathspec_module: Any,
) -> IndexExecutionResult:
    """Execute a checkpointed repo-batch index request."""

    repo_file_sets = resolve_repository_file_sets(
        builder,
        root_path,
        selected_repositories=selected_repositories,
        pathspec_module=pathspec_module,
    )
    repo_paths = list(repo_file_sets.keys())
    if not repo_paths:
        if job_id:
            builder.job_manager.update_job(
                job_id,
                status=job_status_enum.COMPLETED,
                end_time=datetime_cls.now(),
                result={"repository_count": 0},
            )
        return IndexExecutionResult(
            run_id="",
            root_path=root_path.resolve(),
            repository_count=0,
            completed_repositories=0,
            failed_repositories=0,
            resumed_repositories=0,
            skipped_repositories=0,
            finalization_status="skipped",
            status="completed",
        )

    run_state, resumed = _load_or_create_run(
        root_path=root_path.resolve(),
        family=family,
        source=source,
        repo_paths=repo_paths,
        is_dependency=is_dependency,
    )
    if force:
        _archive_run(run_state.run_id, reason="Force reindex requested")
        _record_checkpoint_metric(
            component=component,
            mode=family,
            source=source,
            operation="invalidate",
            status="completed",
        )
        run_state, resumed = _load_or_create_run(
            root_path=root_path.resolve(),
            family=family,
            source=source,
            repo_paths=repo_paths,
            is_dependency=is_dependency,
        )

    total_files = sum(len(files) for files in repo_file_sets.values())
    if job_id:
        builder.job_manager.update_job(
            job_id,
            status=job_status_enum.RUNNING,
            total_files=total_files,
        )

    telemetry = get_observability()
    resumed_repositories = sum(
        1
        for repo_state in run_state.repositories.values()
        if repo_state.status in {"failed", "parsed", "running", "commit_incomplete"}
    )
    skipped_repositories = sum(
        1 for repo_state in run_state.repositories.values() if repo_state.status == "skipped"
    )
    _update_pending_repository_gauge(
        component=component,
        mode=family,
        source=source,
        pending_count=run_state.pending_repositories(),
    )
    with telemetry.index_run(
        component=component,
        mode=family,
        source=source,
        repo_count=len(repo_paths),
        run_id=run_state.run_id,
        resume=resumed,
    ) as run_scope:
        snapshots: list[RepositorySnapshot] = []
        merged_imports_map: dict[str, list[str]] = {}

        for repo_path in repo_paths:
            repo_state = run_state.repositories[str(repo_path.resolve())]
            if repo_state.status == "completed":
                snapshot = _load_snapshot(run_state.run_id, repo_path)
                if snapshot is not None:
                    snapshots.append(snapshot)
                    merge_import_maps(merged_imports_map, snapshot.imports_map)
                else:
                    repo_state.status = "pending"
                    repo_state.error = "Completed repo snapshot missing; re-parsing repository"
                    _persist_run_state(run_state)
                continue

            started = time.perf_counter()
            repo_state.started_at = _utc_now()
            repo_state.finished_at = None
            repo_state.error = None
            repo_state.status = "running"
            _persist_run_state(run_state)
            _record_checkpoint_metric(
                component=component,
                mode=family,
                source=source,
                operation="save",
                status="completed",
            )
            _update_pending_repository_gauge(
                component=component,
                mode=family,
                source=source,
                pending_count=run_state.pending_repositories(),
            )
            telemetry.record_index_repositories(
                component=component,
                phase="started",
                count=1,
                mode=family,
                source=source,
            )
            if resumed and repo_state.status in ACTIVE_REPO_STATES:
                telemetry.record_index_repositories(
                    component=component,
                    phase="resumed",
                    count=1,
                    mode=family,
                    source=source,
                )

            with telemetry.start_span(
                "pcg.index.repository",
                component=component,
                attributes={
                    "pcg.index.run_id": run_state.run_id,
                    "pcg.index.repo_path": str(repo_path.resolve()),
                    "pcg.index.resume": resumed,
                },
            ) as repo_span:
                commit_started = False
                try:
                    snapshot = await parse_repository_snapshot_async(
                        builder,
                        repo_path,
                        repo_file_sets[repo_path],
                        is_dependency=is_dependency,
                        job_id=job_id,
                        asyncio_module=asyncio_module,
                        info_logger_fn=info_logger_fn,
                    )
                    repo_state.file_count = snapshot.file_count
                    repo_state.status = "parsed"
                    _save_snapshot(run_state.run_id, snapshot)
                    _record_checkpoint_metric(
                        component=component,
                        mode=family,
                        source=source,
                        operation="save",
                        status="completed",
                    )
                    _persist_run_state(run_state)
                    commit_started = True
                    repo_state.status = "commit_incomplete"
                    _persist_run_state(run_state)
                    _commit_repository_snapshot(
                        builder,
                        snapshot,
                        is_dependency=is_dependency,
                    )
                    snapshots.append(snapshot)
                    merge_import_maps(merged_imports_map, snapshot.imports_map)
                    repo_state.status = "completed"
                    repo_state.finished_at = _utc_now()
                    _persist_run_state(run_state)
                    telemetry.record_index_repositories(
                        component=component,
                        phase="completed",
                        count=1,
                        mode=family,
                        source=source,
                    )
                    telemetry.record_index_repository_duration(
                        component=component,
                        mode=family,
                        source=source,
                        status="completed",
                        duration_seconds=time.perf_counter() - started,
                    )
                except Exception as exc:
                    repo_state.error = str(exc)
                    repo_state.finished_at = _utc_now()
                    repo_state.status = (
                        "commit_incomplete" if commit_started else "failed"
                    )
                    run_state.last_error = str(exc)
                    _persist_run_state(run_state)
                    phase = (
                        "commit_incomplete"
                        if repo_state.status == "commit_incomplete"
                        else "failed"
                    )
                    telemetry.record_index_repositories(
                        component=component,
                        phase=phase,
                        count=1,
                        mode=family,
                        source=source,
                    )
                    telemetry.record_index_repository_duration(
                        component=component,
                        mode=family,
                        source=source,
                        status=phase,
                        duration_seconds=time.perf_counter() - started,
                    )
                    if repo_span is not None:
                        repo_span.record_exception(exc)
                    warning_logger_fn(
                        f"Failed to index repository {repo_path.resolve()}: {exc}"
                    )
                finally:
                    _update_pending_repository_gauge(
                        component=component,
                        mode=family,
                        source=source,
                        pending_count=run_state.pending_repositories(),
                    )

        if run_state.failed_repositories() == 0:
            run_state.finalization_status = "running"
            _persist_run_state(run_state)
            with telemetry.start_span(
                "pcg.index.finalize",
                component=component,
                attributes={
                    "pcg.index.run_id": run_state.run_id,
                    "pcg.index.repo_count": len(repo_paths),
                },
            ) as finalize_span:
                try:
                    finalize_index_batch(
                        builder,
                        snapshots=snapshots,
                        merged_imports_map=merged_imports_map,
                        info_logger_fn=info_logger_fn,
                    )
                    run_state.finalization_status = "completed"
                    run_state.status = "completed"
                    _persist_run_state(run_state)
                    _delete_snapshots(run_state.run_id)
                except Exception as exc:
                    run_state.status = "failed"
                    run_state.finalization_status = "failed"
                    run_state.last_error = str(exc)
                    _persist_run_state(run_state)
                    if finalize_span is not None:
                        finalize_span.record_exception(exc)
                    error_logger_fn(
                        f"Failed to finalize repository batch for {root_path.resolve()}: {exc}"
                    )
        else:
            run_state.status = "partial_failure"
            run_state.finalization_status = "pending"
            _persist_run_state(run_state)

        run_scope.status = run_state.status
        run_scope.finalization_status = run_state.finalization_status
        _update_pending_repository_gauge(
            component=component,
            mode=family,
            source=source,
            pending_count=run_state.pending_repositories(),
        )

    if job_id:
        final_status = (
            job_status_enum.COMPLETED
            if run_state.status == "completed"
            else job_status_enum.FAILED
        )
        errors = [run_state.last_error] if run_state.last_error else []
        builder.job_manager.update_job(
            job_id,
            status=final_status,
            end_time=datetime_cls.now(),
            errors=errors,
            result={
                "run_id": run_state.run_id,
                "repository_count": len(repo_paths),
                "completed_repositories": run_state.completed_repositories(),
                "failed_repositories": run_state.failed_repositories(),
                "finalization_status": run_state.finalization_status,
                "status": run_state.status,
            },
        )

    return IndexExecutionResult(
        run_id=run_state.run_id,
        root_path=root_path.resolve(),
        repository_count=len(repo_paths),
        completed_repositories=run_state.completed_repositories(),
        failed_repositories=run_state.failed_repositories(),
        resumed_repositories=resumed_repositories,
        skipped_repositories=skipped_repositories,
        finalization_status=run_state.finalization_status,
        status=run_state.status,
    )


def raise_for_failed_index_run(result: IndexExecutionResult) -> None:
    """Raise a runtime error when a coordinated run did not finish cleanly."""

    if result.status == "completed":
        return
    raise RuntimeError(
        "Index run "
        f"{result.run_id or '<empty>'} finished with status {result.status} "
        f"(completed={result.completed_repositories}, failed={result.failed_repositories}, "
        f"finalization={result.finalization_status})"
    )


def describe_latest_index_run(path: Path) -> dict[str, Any] | None:
    """Return the latest persisted run summary for a root path."""

    matches = _matching_run_states(path.resolve())
    if not matches:
        return None
    latest = matches[0]
    return {
        "run_id": latest.run_id,
        "root_path": latest.root_path,
        "family": latest.family,
        "source": latest.source,
        "status": latest.status,
        "finalization_status": latest.finalization_status,
        "created_at": latest.created_at,
        "updated_at": latest.updated_at,
        "last_error": latest.last_error,
        "repository_count": len(latest.repositories),
        "completed_repositories": latest.completed_repositories(),
        "failed_repositories": latest.failed_repositories(),
        "pending_repositories": latest.pending_repositories(),
    }
