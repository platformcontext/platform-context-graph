"""Checkpoint persistence helpers for resumable indexing."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Sequence

from platform_context_graph.core.database import (
    GraphStoreCapabilities,
    graph_store_capabilities_for_backend,
)
from platform_context_graph.observability import get_observability
from platform_context_graph.paths import get_app_home

from .coordinator_models import (
    IndexRunState,
    RepositoryRunState,
    RepositorySnapshot,
    RepositorySnapshotMetadata,
)

RUNS_DIRNAME = "index-runs"
RUN_STATE_FILENAME = "run.json"
SNAPSHOT_DIRNAME = "snapshots"


@dataclass(frozen=True)
class GraphStoreAdapter:
    """Narrow graph-store contract used by coordinator-backed indexing."""

    capabilities: GraphStoreCapabilities
    initialize_schema: Callable[[], None]
    delete_repository: Callable[[str], bool]


def _graph_store_adapter(builder: Any) -> GraphStoreAdapter:
    """Return the narrow graph-store contract for one builder instance."""

    capabilities_getter = getattr(builder.db_manager, "graph_store_capabilities", None)
    capabilities = (
        capabilities_getter()
        if callable(capabilities_getter)
        else graph_store_capabilities_for_backend(
            getattr(builder.db_manager, "get_backend_type", lambda: "neo4j")()
        )
    )
    return GraphStoreAdapter(
        capabilities=capabilities,
        initialize_schema=builder.create_schema,
        delete_repository=builder.delete_repository_from_graph,
    )


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


def _snapshot_key(repo_path: Path) -> str:
    """Return the stable storage key for one repository snapshot."""

    return sha256(str(repo_path.resolve()).encode("utf-8")).hexdigest()[:16]


def _snapshot_path(run_id: str, repo_path: Path) -> Path:
    """Return the legacy staged snapshot file path for one repository."""

    return _snapshot_dir(run_id) / f"{_snapshot_key(repo_path)}.json"


def _snapshot_metadata_path(run_id: str, repo_path: Path) -> Path:
    """Return the staged metadata file path for one repository."""

    return _snapshot_dir(run_id) / f"{_snapshot_key(repo_path)}.meta.json"


def _snapshot_file_data_path(run_id: str, repo_path: Path) -> Path:
    """Return the staged file-data file path for one repository."""

    return _snapshot_dir(run_id) / f"{_snapshot_key(repo_path)}.files.ndjson"


def _legacy_snapshot_file_data_path(run_id: str, repo_path: Path) -> Path:
    """Return the legacy JSON file-data path for one repository."""

    return _snapshot_dir(run_id) / f"{_snapshot_key(repo_path)}.files.json"


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
        finalization_started_at=payload.get("finalization_started_at"),
        finalization_finished_at=payload.get("finalization_finished_at"),
        finalization_duration_seconds=payload.get("finalization_duration_seconds"),
        finalization_current_stage=payload.get("finalization_current_stage"),
        finalization_stage_started_at=payload.get("finalization_stage_started_at"),
        finalization_stage_durations=dict(
            payload.get("finalization_stage_durations", {})
        ),
        finalization_stage_details=dict(payload.get("finalization_stage_details", {})),
        last_error=payload.get("last_error"),
        repositories=repositories,
    )


def _json_default(obj: Any) -> str:
    """Fallback serializer for ``json.dumps``.

    Only converts ``Path`` objects; everything else raises so that
    unexpected types surface as bugs rather than being silently stringified.
    """

    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically using temp-file-plus-rename semantics."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default),
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


def _load_run_state_by_id(run_id: str) -> IndexRunState | None:
    """Load a checkpoint state by run identifier."""

    return _load_run_state(_run_state_path(run_id))


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

    with get_observability().start_span(
        "pcg.index.checkpoint.save_run_state",
        component=state.family,
        attributes={"pcg.index.run_id": state.run_id},
    ):
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
        if run.family == family
        and run.source == source
        and run.is_dependency == is_dependency
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
            str(repo_path.resolve()): RepositoryRunState(
                repo_path=str(repo_path.resolve())
            )
            for repo_path in _normalize_paths(repo_paths)
        },
    )
    _persist_run_state(state)
    return state, False


def _save_snapshot(run_id: str, snapshot: RepositorySnapshot) -> None:
    """Persist one parsed repository snapshot to disk."""

    repo_path = Path(snapshot.repo_path)
    _save_snapshot_file_data(run_id, repo_path, snapshot.file_data)
    _save_snapshot_metadata(
        run_id,
        RepositorySnapshotMetadata(
            repo_path=snapshot.repo_path,
            file_count=snapshot.file_count,
            imports_map=snapshot.imports_map,
        ),
    )


def _save_snapshot_metadata(
    run_id: str, snapshot_metadata: RepositorySnapshotMetadata
) -> None:
    """Persist one repository's lightweight snapshot metadata."""

    with get_observability().start_span(
        "pcg.index.checkpoint.save_snapshot_metadata",
        attributes={
            "pcg.index.run_id": run_id,
            "pcg.index.repo_path": snapshot_metadata.repo_path,
        },
    ):
        _write_json_atomic(
            _snapshot_metadata_path(run_id, Path(snapshot_metadata.repo_path)),
            _normalize_json_value(asdict(snapshot_metadata)),
        )


def _save_snapshot_file_data(
    run_id: str, repo_path: Path, file_data: list[dict[str, Any]]
) -> None:
    """Persist one repository's heavyweight file-data payload."""

    with get_observability().start_span(
        "pcg.index.checkpoint.save_snapshot_file_data",
        attributes={
            "pcg.index.run_id": run_id,
            "pcg.index.repo_path": str(repo_path.resolve()),
            "pcg.index.file_data_rows": len(file_data),
        },
    ):
        path = _snapshot_file_data_path(run_id, repo_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            for item in file_data:
                handle.write(json.dumps(_normalize_json_value(item), sort_keys=True))
                handle.write("\n")
        os.replace(tmp_path, path)


def _load_snapshot_metadata(
    run_id: str, repo_path: Path
) -> RepositorySnapshotMetadata | None:
    """Load one staged snapshot metadata payload when present."""

    with get_observability().start_span(
        "pcg.index.checkpoint.load_snapshot_metadata",
        attributes={
            "pcg.index.run_id": run_id,
            "pcg.index.repo_path": str(repo_path.resolve()),
        },
    ):
        metadata_path = _snapshot_metadata_path(run_id, repo_path)
        if metadata_path.exists():
            return RepositorySnapshotMetadata(
                **json.loads(metadata_path.read_text(encoding="utf-8"))
            )

        legacy_path = _snapshot_path(run_id, repo_path)
        if not legacy_path.exists():
            return None
        payload = json.loads(legacy_path.read_text(encoding="utf-8"))
        return RepositorySnapshotMetadata(
            repo_path=payload["repo_path"],
            file_count=payload["file_count"],
            imports_map=dict(payload.get("imports_map", {})),
        )


def _load_snapshot_file_data(
    run_id: str, repo_path: Path
) -> list[dict[str, Any]] | None:
    """Load one staged snapshot file-data payload when present."""

    with get_observability().start_span(
        "pcg.index.checkpoint.load_snapshot_file_data",
        attributes={
            "pcg.index.run_id": run_id,
            "pcg.index.repo_path": str(repo_path.resolve()),
        },
    ):
        file_data_path = _snapshot_file_data_path(run_id, repo_path)
        if file_data_path.exists():
            with file_data_path.open(encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]

        legacy_file_data_path = _legacy_snapshot_file_data_path(run_id, repo_path)
        if legacy_file_data_path.exists():
            payload = json.loads(legacy_file_data_path.read_text(encoding="utf-8"))
            return list(payload.get("file_data", []))

        legacy_path = _snapshot_path(run_id, repo_path)
        if not legacy_path.exists():
            return None
        payload = json.loads(legacy_path.read_text(encoding="utf-8"))
        return list(payload.get("file_data", []))


def _iter_snapshot_file_data_batches(
    run_id: str,
    repo_path: Path,
    *,
    batch_size: int,
):
    """Yield one repository snapshot's file-data in bounded batches."""

    file_data_path = _snapshot_file_data_path(run_id, repo_path)
    if file_data_path.exists():
        batch: list[dict[str, Any]] = []
        with file_data_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                batch.append(json.loads(line))
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch
        return

    file_data = _load_snapshot_file_data(run_id, repo_path)
    if file_data is None:
        raise FileNotFoundError(
            f"Missing file data snapshot for committed repository {repo_path.resolve()}"
        )
    for start in range(0, len(file_data), batch_size):
        yield file_data[start : start + batch_size]


def _iter_snapshot_file_data(run_id: str, repo_path: Path):
    """Yield one repository snapshot's file-data one payload at a time."""

    for batch in _iter_snapshot_file_data_batches(
        run_id,
        repo_path,
        batch_size=128,
    ):
        yield from batch


def _snapshot_file_data_exists(run_id: str, repo_path: Path) -> bool:
    """Return whether heavyweight file-data exists for one snapshot."""

    return (
        _snapshot_file_data_path(run_id, repo_path).exists()
        or _legacy_snapshot_file_data_path(run_id, repo_path).exists()
        or _snapshot_path(run_id, repo_path).exists()
    )


def _load_snapshot(run_id: str, repo_path: Path) -> RepositorySnapshot | None:
    """Load one staged snapshot when present."""

    metadata = _load_snapshot_metadata(run_id, repo_path)
    file_data = _load_snapshot_file_data(run_id, repo_path)
    if metadata is None or file_data is None:
        return None
    return RepositorySnapshot(
        repo_path=metadata.repo_path,
        file_count=metadata.file_count,
        imports_map=metadata.imports_map,
        file_data=file_data,
    )


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
