"""Checkpoint persistence helpers for resumable indexing."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from platform_context_graph.observability import get_observability
from platform_context_graph.paths import get_app_home

from .coordinator_models import IndexRunState, RepositoryRunState, RepositorySnapshot

RUNS_DIRNAME = "index-runs"
RUN_STATE_FILENAME = "run.json"
SNAPSHOT_DIRNAME = "snapshots"


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


def _normalize_json_value(value: Any) -> Any:
    """Convert checkpoint payload values into JSON-serializable structures."""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, set):
        return sorted(_normalize_json_value(item) for item in value)
    return value


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

    _write_json_atomic(
        _snapshot_path(run_id, Path(snapshot.repo_path)),
        _normalize_json_value(asdict(snapshot)),
    )


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
