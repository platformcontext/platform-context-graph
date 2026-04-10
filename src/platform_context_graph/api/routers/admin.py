"""Administrative API endpoints for graph maintenance operations."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies import get_database
from ...query.status import request_ingester_reindex_control
from ...query.shared_projection_tuning import build_tuning_report
from ...core.jobs import JobManager
from ...runtime.status_store_runtime import (
    update_latest_repository_coverage_finalization,
)
from ...tools.graph_builder import GraphBuilder
from ...collectors.git.finalize import finalize_index_batch
from ...utils.debug_log import info_logger, warning_logger
from .admin_facts import ReplayFailedFactsRequest
from .admin_facts import replay_failed_facts

router = APIRouter(prefix="/admin", tags=["admin"])
_SUPPORTED_ADMIN_STAGES = frozenset({"workloads", "relationship_resolution"})
_DEFAULT_ADMIN_STAGES = ["workloads", "relationship_resolution"]


class RefinalizeRequest(BaseModel):
    """Request body for the admin re-finalization endpoint."""

    stages: list[str] | None = None
    repo_ids: list[str] | None = None


class ReindexRequest(BaseModel):
    """Request body for the admin reindex endpoint."""

    ingester: str = "repository"
    scope: str = "workspace"
    force: bool = True


_finalization_lock = threading.Lock()
_finalization_state: dict[str, Any] = {
    "running": False,
    "run_id": None,
    "stages": None,
    "current_stage": None,
    "stage_details": {},
    "targeted_repo_ids": [],
    "targeted_repo_count": 0,
    "last_run_at": None,
    "last_duration_seconds": None,
    "last_timings": None,
    "last_error": None,
    "repo_count": 0,
}


def _update_finalization_state(**updates: Any) -> None:
    """Mutate the in-memory admin finalization state under the shared lock."""

    with _finalization_lock:
        _finalization_state.update(updates)


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_target_repositories(
    database: Any,
    *,
    repo_ids: list[str] | None,
) -> list[dict[str, str]]:
    """Resolve the targeted repositories from the graph, validating repo IDs."""

    requested_repo_ids = list(dict.fromkeys(repo_ids or []))
    driver = database.get_driver()
    with driver.session() as session:
        rows = session.run(
            """
            MATCH (r:Repository)
            WHERE $repo_ids IS NULL OR r.id IN $repo_ids
            RETURN r.id AS repo_id, r.path AS p
            ORDER BY r.path
            """,
            repo_ids=requested_repo_ids or None,
        ).data()

    repo_records = [
        {
            "repo_id": str(row.get("repo_id") or "").strip(),
            "repo_path": str(row.get("p") or row.get("path") or "").strip(),
        }
        for row in rows
        if row.get("repo_id") and (row.get("p") or row.get("path"))
    ]
    if requested_repo_ids:
        resolved_repo_ids = {record["repo_id"] for record in repo_records}
        missing_repo_ids = [
            repo_id
            for repo_id in requested_repo_ids
            if repo_id not in resolved_repo_ids
        ]
        if missing_repo_ids:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Unknown repository ids for admin refinalize: "
                    + ", ".join(missing_repo_ids)
                ),
            )
    return repo_records


def _repair_repository_coverage(
    *,
    repo_ids: list[str],
    finalization_status: str,
    last_error: str | None,
    run_id: str,
) -> None:
    """Repair the latest durable coverage rows for the targeted repositories."""

    if not repo_ids:
        return
    info_logger(
        "Repairing durable repository coverage after admin re-finalize",
        event_name="admin.refinalize.coverage_repair.started",
        extra_keys={
            "run_id": run_id,
            "repo_count": len(repo_ids),
            "finalization_status": finalization_status,
        },
    )
    update_latest_repository_coverage_finalization(
        repo_ids=repo_ids,
        finalization_status=finalization_status,
        finalization_finished_at=_utc_now_iso(),
        last_error=last_error,
    )
    info_logger(
        "Finished durable repository coverage repair after admin re-finalize",
        event_name="admin.refinalize.coverage_repair.completed",
        extra_keys={
            "run_id": run_id,
            "repo_count": len(repo_ids),
            "finalization_status": finalization_status,
        },
    )


def _run_refinalization(
    database: Any,
    repo_records: list[dict[str, str]],
    run_id: str,
    stages: list[str],
) -> None:
    """Execute re-finalization in a dedicated thread.

    This admin path intentionally supports only graph-safe stages.
    """

    loop = asyncio.new_event_loop()
    repo_ids = [record["repo_id"] for record in repo_records]
    repo_paths = [Path(record["repo_path"]) for record in repo_records]
    try:
        asyncio.set_event_loop(loop)
        _update_finalization_state(
            repo_count=len(repo_paths),
            current_stage=None,
            stage_details={"status": "started", "run_id": run_id},
        )
        info_logger(
            f"Re-finalization started for {len(repo_paths)} repositories",
            event_name="admin.refinalize.started",
            extra_keys={
                "run_id": run_id,
                "repo_count": len(repo_paths),
                "stages": stages,
                "targeted_repo_ids": repo_ids,
            },
        )

        job_mgr = JobManager()
        builder = GraphBuilder(db_manager=database, job_manager=job_mgr, loop=loop)

        start = time.time()
        timings = finalize_index_batch(
            builder,
            committed_repo_paths=repo_paths,
            iter_snapshot_file_data_fn=lambda p: iter([]),
            merged_imports_map={},
            info_logger_fn=info_logger,
            stage_progress_callback=lambda stage, **kw: (
                _update_finalization_state(
                    current_stage=stage if kw.get("status") != "completed" else None,
                    stage_details={
                        "stage": stage,
                        **kw,
                    },
                ),
                info_logger(
                    f"Re-finalization stage update: {stage}",
                    event_name="admin.refinalize.stage",
                    extra_keys={"stage": stage, "run_id": run_id, **kw},
                ),
            ),
            run_id=run_id,
            skip_per_repo_stages=False,
            stages=stages,
        )
        elapsed = time.time() - start
        _repair_repository_coverage(
            repo_ids=repo_ids,
            finalization_status="completed",
            last_error=None,
            run_id=run_id,
        )
        _update_finalization_state(
            last_run_at=_utc_now_iso(),
            last_duration_seconds=round(elapsed, 1),
            last_timings={k: round(v, 2) for k, v in (timings or {}).items()},
            last_error=None,
            current_stage=None,
            stage_details={"status": "completed", "run_id": run_id},
        )

        info_logger(
            f"Re-finalization completed in {elapsed:.1f}s",
            event_name="admin.refinalize.completed",
            extra_keys={
                "run_id": run_id,
                "duration_seconds": elapsed,
                "timings": timings,
            },
        )
    except Exception as exc:
        try:
            _repair_repository_coverage(
                repo_ids=repo_ids,
                finalization_status="failed",
                last_error=str(exc),
                run_id=run_id,
            )
        except Exception as coverage_exc:
            warning_logger(
                f"Coverage repair failed after admin refinalize error: {coverage_exc}",
                event_name="admin.refinalize.coverage_repair.failed",
                exc_info=coverage_exc,
                extra_keys={"run_id": run_id},
            )
        _update_finalization_state(
            last_error=str(exc),
            current_stage=None,
            stage_details={"status": "failed", "run_id": run_id},
        )
        warning_logger(
            f"Re-finalization failed: {exc}",
            event_name="admin.refinalize.failed",
            exc_info=exc,
            extra_keys={"run_id": run_id},
        )
    finally:
        _update_finalization_state(running=False)
        loop.close()


@router.post("/refinalize")
async def refinalize(
    payload: RefinalizeRequest | None = None,
    database: Any = Depends(get_database),
) -> dict[str, Any]:
    """Trigger re-finalization of all indexed repositories.

    Executes in a background thread and returns immediately. Status is
    per-process and not shared across workers.
    """

    payload = payload or RefinalizeRequest()
    requested_stages = payload.stages or list(_DEFAULT_ADMIN_STAGES)
    invalid_stages = sorted(set(requested_stages) - _SUPPORTED_ADMIN_STAGES)
    if invalid_stages:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported admin refinalize stages: " + ", ".join(invalid_stages)
            ),
        )
    if payload.repo_ids and "relationship_resolution" in requested_stages:
        raise HTTPException(
            status_code=400,
            detail=(
                "Stage 'relationship_resolution' does not support repo_ids in "
                "admin refinalize because it remains full-generation."
            ),
        )
    repo_records = _load_target_repositories(database, repo_ids=payload.repo_ids)
    run_id = f"refinalize-api-{uuid4().hex[:12]}"
    targeted_repo_ids = [record["repo_id"] for record in repo_records]

    with _finalization_lock:
        if _finalization_state["running"]:
            return {
                "status": "already_running",
                "message": "Re-finalization is already in progress.",
                "run_id": _finalization_state.get("run_id"),
                "stages": _finalization_state.get("stages"),
                "repo_count": _finalization_state["repo_count"],
                "targeted_repo_ids": list(
                    _finalization_state.get("targeted_repo_ids") or []
                ),
                "targeted_repo_count": _finalization_state.get(
                    "targeted_repo_count", 0
                ),
            }
        _finalization_state.update(
            {
                "running": True,
                "run_id": run_id,
                "stages": requested_stages,
                "current_stage": None,
                "stage_details": {"status": "queued", "run_id": run_id},
                "targeted_repo_ids": targeted_repo_ids,
                "targeted_repo_count": len(targeted_repo_ids),
                "last_error": None,
                "repo_count": len(repo_records),
            }
        )

    thread = threading.Thread(
        target=_run_refinalization,
        args=(database, repo_records, run_id, requested_stages),
        name="refinalize-worker",
        daemon=True,
    )
    thread.start()

    return {
        "status": "started",
        "message": "Re-finalization started in background thread.",
        "run_id": run_id,
        "stages": requested_stages,
        "targeted_repo_ids": targeted_repo_ids,
        "targeted_repo_count": len(targeted_repo_ids),
    }


@router.get("/refinalize/status")
async def refinalize_status() -> dict[str, Any]:
    """Return the current re-finalization status.

    Note: status is per-process and not shared across workers.
    """

    return {
        "running": _finalization_state["running"],
        "run_id": _finalization_state.get("run_id"),
        "stages": _finalization_state.get("stages"),
        "current_stage": _finalization_state.get("current_stage"),
        "stage_details": _finalization_state.get("stage_details"),
        "targeted_repo_ids": list(_finalization_state.get("targeted_repo_ids") or []),
        "targeted_repo_count": _finalization_state.get("targeted_repo_count", 0),
        "last_run_at": _finalization_state["last_run_at"],
        "last_duration_seconds": _finalization_state["last_duration_seconds"],
        "last_timings": _finalization_state["last_timings"],
        "last_error": _finalization_state["last_error"],
        "repo_count": _finalization_state["repo_count"],
    }


@router.get("/shared-projection/tuning-report")
async def shared_projection_tuning_report(
    include_platform: bool = False,
) -> dict[str, Any]:
    """Return the deterministic shared-write tuning report payload."""

    return build_tuning_report(include_platform=include_platform)


@router.post("/reindex")
async def reindex(
    payload: ReindexRequest | None = None,
    database: Any = Depends(get_database),
) -> dict[str, Any]:
    """Persist a full reindex request for the ingester to claim asynchronously."""

    payload = payload or ReindexRequest()
    normalized_ingester = str(payload.ingester or "repository").strip().lower()
    normalized_scope = str(payload.scope or "workspace").strip().lower()
    if normalized_ingester != "repository":
        raise HTTPException(
            status_code=404,
            detail=f"Unknown ingester for admin reindex: {payload.ingester}",
        )
    if normalized_scope != "workspace":
        raise HTTPException(
            status_code=400,
            detail="Admin reindex currently supports only scope='workspace'.",
        )

    result = request_ingester_reindex_control(
        database,
        ingester=normalized_ingester,
        requested_by="api",
        force=bool(payload.force),
        scope=normalized_scope,
    )
    return {
        "status": "accepted" if result.get("accepted", True) else "unavailable",
        "ingester": normalized_ingester,
        "request_token": result.get("reindex_request_token"),
        "request_state": result.get("reindex_request_state"),
        "requested_at": result.get("reindex_requested_at"),
        "requested_by": result.get("reindex_requested_by"),
        "force": bool(result.get("requested_force", payload.force)),
        "scope": result.get("requested_scope") or normalized_scope,
        "run_id": result.get("run_id"),
    }
