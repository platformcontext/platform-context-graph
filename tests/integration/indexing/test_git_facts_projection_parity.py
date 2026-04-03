"""Integration checks for workload and platform projection inputs from facts."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.facts.emission.git_snapshot import emit_git_snapshot_facts
from platform_context_graph.resolution.projection.workloads import (
    project_platform_facts,
)
from platform_context_graph.resolution.projection.workloads import (
    project_workload_facts,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for projection parity tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_emitted_git_facts_preserve_workload_and_platform_repo_inputs() -> None:
    """Workload/platform projection should target the same repository from facts."""

    fact_store = MagicMock()
    work_queue = MagicMock()
    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/service",
        file_count=1,
        imports_map={},
        file_data=[
            {
                "path": "/tmp/service/src/app.py",
                "repo_path": "/tmp/service",
                "lang": "python",
                "functions": [{"name": "handler", "line_number": 10}],
            }
        ],
    )

    emit_git_snapshot_facts(
        snapshot=snapshot,
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        is_dependency=False,
        fact_store=fact_store,
        work_queue=work_queue,
        observed_at=_utc_now(),
    )
    fact_records = fact_store.upsert_facts.call_args.args[0]
    captured: dict[str, object] = {}
    workload_progress = MagicMock()
    platform_progress = MagicMock()
    builder = SimpleNamespace()

    def _materialize_workloads(
        builder,
        *,
        committed_repo_paths,
        info_logger_fn,
        progress_callback=None,
    ) -> dict[str, int]:
        captured["workloads_builder"] = builder
        captured["workloads_info_logger_fn"] = info_logger_fn
        captured["workloads_progress_callback"] = progress_callback
        captured["workloads_repo_paths"] = list(committed_repo_paths)
        return {"workloads_projected": len(committed_repo_paths)}

    class _Session:
        def __enter__(self) -> "_Session":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def _materialize_platforms(
        session,
        *,
        repo_paths,
        progress_callback=None,
    ) -> dict[str, int]:
        captured["platform_session"] = session
        captured["platform_repo_paths"] = list(repo_paths)
        captured["platform_progress_callback"] = progress_callback
        return {"platform_edges": len(repo_paths)}

    workload_metrics = project_workload_facts(
        builder=builder,
        fact_records=fact_records,
        materialize_workloads_fn=_materialize_workloads,
        info_logger_fn=MagicMock(),
        progress_callback=workload_progress,
    )
    platform_metrics = project_platform_facts(
        builder=SimpleNamespace(driver=SimpleNamespace(session=lambda: _Session())),
        fact_records=fact_records,
        materialize_platforms_fn=_materialize_platforms,
        progress_callback=platform_progress,
    )

    expected_repo_path = Path("/tmp/service").resolve()
    assert captured["workloads_builder"] is builder
    assert captured["workloads_info_logger_fn"] is not None
    assert captured["workloads_progress_callback"] is workload_progress
    assert captured["workloads_repo_paths"] == [expected_repo_path]
    assert captured["platform_repo_paths"] == [expected_repo_path]
    assert captured["platform_progress_callback"] is platform_progress
    assert workload_metrics == {"workloads_projected": 1}
    assert platform_metrics == {"platform_edges": 1}
