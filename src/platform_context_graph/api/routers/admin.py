"""Administrative API endpoints for graph maintenance operations."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from ..dependencies import get_database
from ...core.jobs import JobManager
from ...tools.graph_builder import GraphBuilder
from ...tools.graph_builder_indexing_finalize import finalize_index_batch
from ...utils.debug_log import info_logger, warning_logger

router = APIRouter(prefix="/admin", tags=["admin"])

_finalization_lock = threading.Lock()
_finalization_state: dict[str, Any] = {
    "running": False,
    "last_run_at": None,
    "last_duration_seconds": None,
    "last_timings": None,
    "last_error": None,
    "repo_count": 0,
}


def _run_refinalization(database: Any) -> None:
    """Execute re-finalization in a dedicated thread.

    Note: inheritance, function_calls and infra_links stages are
    effectively no-ops without snapshot file data. The primary value
    is re-running workloads and relationship_resolution which operate
    directly on the graph.
    """

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        driver = database.get_driver()

        with driver.session() as session:
            paths = session.run(
                "MATCH (r:Repository) RETURN r.path AS p ORDER BY r.path"
            ).data()
            repo_paths = [Path(r["p"]) for r in paths if r.get("p")]

        _finalization_state["repo_count"] = len(repo_paths)
        info_logger(
            f"Re-finalization started for {len(repo_paths)} repositories",
            event_name="admin.refinalize.started",
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
            stage_progress_callback=lambda stage, **kw: info_logger(
                f"Re-finalization stage: {stage}",
                event_name="admin.refinalize.stage",
                extra_keys={"stage": stage},
            ),
            run_id=f"refinalize-api-{int(time.time())}",
            skip_per_repo_stages=False,
        )
        elapsed = time.time() - start

        _finalization_state["last_run_at"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )
        _finalization_state["last_duration_seconds"] = round(elapsed, 1)
        _finalization_state["last_timings"] = {
            k: round(v, 2) for k, v in (timings or {}).items()
        }

        info_logger(
            f"Re-finalization completed in {elapsed:.1f}s",
            event_name="admin.refinalize.completed",
            extra_keys={"duration_seconds": elapsed, "timings": timings},
        )
    except Exception as exc:
        _finalization_state["last_error"] = str(exc)
        warning_logger(
            f"Re-finalization failed: {exc}",
            event_name="admin.refinalize.failed",
            exc_info=exc,
        )
    finally:
        _finalization_state["running"] = False
        loop.close()


@router.post("/refinalize")
async def refinalize(
    database: Any = Depends(get_database),
) -> dict[str, Any]:
    """Trigger re-finalization of all indexed repositories.

    Re-runs workloads and relationship resolution across the entire
    graph. Executes in a background thread and returns immediately.

    Note: status is per-process and not shared across workers.
    """

    with _finalization_lock:
        if _finalization_state["running"]:
            return {
                "status": "already_running",
                "message": "Re-finalization is already in progress.",
                "repo_count": _finalization_state["repo_count"],
            }
        _finalization_state["running"] = True
        _finalization_state["last_error"] = None

    thread = threading.Thread(
        target=_run_refinalization,
        args=(database,),
        name="refinalize-worker",
        daemon=True,
    )
    thread.start()

    return {
        "status": "started",
        "message": "Re-finalization started in background thread.",
    }


@router.get("/refinalize/status")
async def refinalize_status() -> dict[str, Any]:
    """Return the current re-finalization status.

    Note: status is per-process and not shared across workers.
    """

    return {
        "running": _finalization_state["running"],
        "last_run_at": _finalization_state["last_run_at"],
        "last_duration_seconds": _finalization_state["last_duration_seconds"],
        "last_timings": _finalization_state["last_timings"],
        "last_error": _finalization_state["last_error"],
        "repo_count": _finalization_state["repo_count"],
    }
