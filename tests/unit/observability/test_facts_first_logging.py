from __future__ import annotations

import importlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.facts.work_queue.stages import ProjectionStageError
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.indexing.coordinator_facts import (
    emit_repository_snapshot_facts,
)
from platform_context_graph.resolution.orchestration.engine import project_work_item
from platform_context_graph.resolution.orchestration.runtime import (
    run_resolution_iteration,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for facts-first log tests."""

    return datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)


def _configure_buffer(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Configure JSON logging to an in-memory buffer."""

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()
    monkeypatch.setenv("ENABLE_APP_LOGS", "INFO")
    monkeypatch.setenv("PCG_LOG_FORMAT", "json")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    buffer = io.StringIO()
    observability.configure_logging(
        component="resolution-engine",
        runtime_role="resolution-engine",
        stream=buffer,
    )
    return buffer


def _parse_records(buffer: io.StringIO) -> list[dict[str, object]]:
    """Return parsed structured log records from one buffer."""

    return [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]


def test_emit_repository_snapshot_facts_logs_emission_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Facts emission should log a stable structured snapshot summary."""

    buffer = _configure_buffer(monkeypatch)
    snapshot = RepositoryParseSnapshot(
        repo_path=str(tmp_path / "payments"),
        file_count=1,
        imports_map={"app": ["src/app.py"]},
        file_data=[
            {
                "path": str((tmp_path / "payments" / "src" / "app.py").resolve()),
                "lang": "python",
                "functions": [{"name": "main", "line_number": 1}],
                "classes": [],
                "variables": [],
            }
        ],
    )
    fact_store = MagicMock()
    work_queue = MagicMock()

    emit_repository_snapshot_facts(
        source_run_id="run-123",
        repo_path=Path(snapshot.repo_path),
        snapshot=snapshot,
        is_dependency=False,
        fact_store=fact_store,
        work_queue=work_queue,
        observed_at_fn=_utc_now,
    )

    records = _parse_records(buffer)
    emitted = [
        record
        for record in records
        if record.get("event_name") == "facts.snapshot.emitted"
    ]
    assert emitted
    assert emitted[-1]["extra_keys"]["source_run_id"] == "run-123"
    assert emitted[-1]["extra_keys"]["fact_count"] == 3


def test_run_resolution_iteration_logs_dead_letter_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dead-letter paths should emit a structured error breadcrumb."""

    buffer = _configure_buffer(monkeypatch)
    queue = MagicMock()
    queue.claim_work_item.return_value = FactWorkItemRow(
        work_item_id="work-1",
        work_type="project-git-facts",
        repository_id="repository:r_payments",
        source_run_id="run-123",
        lease_owner="resolution-worker-1",
        lease_expires_at=_utc_now(),
        status="leased",
        attempt_count=3,
        created_at=datetime(2026, 4, 3, 11, 0, tzinfo=timezone.utc),
        updated_at=_utc_now(),
    )
    queue.list_queue_snapshot.return_value = []

    run_resolution_iteration(
        queue=queue,
        projector=lambda _row: (_ for _ in ()).throw(RuntimeError("boom")),
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
        max_attempts=3,
    )

    records = _parse_records(buffer)
    dead_lettered = [
        record
        for record in records
        if record.get("event_name") == "resolution.work_item.dead_lettered"
    ]
    assert dead_lettered
    record = dead_lettered[-1]
    assert record["severity_text"] == "ERROR"
    assert record["extra_keys"]["work_item_id"] == "work-1"
    assert record["extra_keys"]["error_class"] == "RuntimeError"


def test_project_work_item_logs_stage_failure_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stage failures should log the stage name and work-item context."""

    buffer = _configure_buffer(monkeypatch)
    fact_store = MagicMock()
    fact_store.list_facts.return_value = []

    with pytest.raises(ProjectionStageError, match="bad relationships") as exc_info:
        project_work_item(
            FactWorkItemRow(
                work_item_id="work-9",
                work_type="project-git-facts",
                repository_id="repository:r_payments",
                source_run_id="run-123",
            ),
            builder=SimpleNamespace(),
            fact_store=fact_store,
            fact_projector=lambda **_kwargs: {"files": 0},
            relationship_projector=lambda **_kwargs: (_ for _ in ()).throw(
                ValueError("bad relationships")
            ),
        )
    assert exc_info.value.stage == "project_relationships"
    assert isinstance(exc_info.value.cause, ValueError)

    records = _parse_records(buffer)
    failures = [
        record
        for record in records
        if record.get("event_name") == "resolution.stage.failed"
    ]
    assert failures
    assert failures[-1]["extra_keys"]["stage"] == "project_relationships"
    assert failures[-1]["extra_keys"]["work_item_id"] == "work-9"


def test_project_work_item_logs_projection_decision_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Projection decisions should emit structured decision breadcrumbs."""

    buffer = _configure_buffer(monkeypatch)
    fact_store = MagicMock()
    fact_store.list_facts.return_value = []
    decision_store = SimpleNamespace(
        upsert_decision=lambda _decision: None,
        insert_evidence=lambda _evidence: None,
    )

    project_work_item(
        FactWorkItemRow(
            work_item_id="work-10",
            work_type="project-git-facts",
            repository_id="repository:r_payments",
            source_run_id="run-123",
        ),
        builder=SimpleNamespace(),
        fact_store=fact_store,
        decision_store=decision_store,
        fact_projector=lambda **_kwargs: {"files": 0},
        relationship_projector=lambda **_kwargs: {"files": 1},
        workload_projector=lambda **_kwargs: {"workloads_projected": 1},
        platform_projector=lambda **_kwargs: {
            "infrastructure_platform_edges_projected": 1
        },
    )

    records = _parse_records(buffer)
    decisions = [
        record
        for record in records
        if record.get("event_name") == "resolution.decision.recorded"
    ]
    assert decisions
    assert decisions[-1]["extra_keys"]["work_item_id"] == "work-10"
    assert decisions[-1]["extra_keys"]["decision_type"] == "project_platforms"
