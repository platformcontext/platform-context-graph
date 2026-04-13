"""Tests for the explicit post-commit writer contract."""

from __future__ import annotations

from types import SimpleNamespace

from platform_context_graph.indexing.post_commit_writer import (
    PostCommitStage,
    execute_post_commit_stages,
)


class _NullSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeObservability:
    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, object]]] = []
        self.durations: list[dict[str, object]] = []

    def start_span(self, name: str, *, attributes: dict[str, object] | None = None):
        self.spans.append((name, dict(attributes or {})))
        return _NullSpan()

    def record_index_stage_duration(self, **kwargs: object) -> None:
        self.durations.append(dict(kwargs))


def test_execute_post_commit_stages_records_timings_and_details() -> None:
    """Stage execution should preserve timings, metrics, and callback details."""

    progress_events: list[tuple[str, dict[str, object]]] = []
    observability = _FakeObservability()

    result = execute_post_commit_stages(
        stages=[
            PostCommitStage(
                name="function_calls",
                runner=lambda: {"resolved_edges": 3, "duration_hint": 1.5},
            ),
            PostCommitStage(
                name="workloads",
                runner=lambda: {"workloads_projected": 2},
            ),
        ],
        info_logger_fn=lambda *_args, **_kwargs: None,
        stage_progress_callback=lambda stage, **kwargs: progress_events.append(
            (stage, kwargs)
        ),
        telemetry=observability,
        component="ingester",
        mode="index",
        source="git",
        parse_strategy="threaded",
        parse_workers=4,
        repo_count=2,
        run_id="run-123",
        monotonic_fn=SimpleNamespace(values=iter([10.0, 11.0, 11.0, 13.5])).__dict__[
            "values"
        ].__next__,
    )

    assert result.stage_timings == {
        "function_calls": 1.0,
        "workloads": 2.5,
    }
    assert result.stage_details == {
        "function_calls": {"resolved_edges": 3, "duration_hint": 1.5},
        "workloads": {"workloads_projected": 2},
    }
    assert progress_events[0] == (
        "function_calls",
        {"status": "started", "repo_count": 2, "run_id": "run-123"},
    )
    assert progress_events[-1] == (
        "workloads",
        {
            "status": "completed",
            "duration_seconds": 2.5,
            "repo_count": 2,
            "run_id": "run-123",
            "workloads_projected": 2,
        },
    )
    assert observability.spans[0][0] == "pcg.index.finalize.stage"
    assert observability.durations[-1]["stage"] == "finalize_workloads"


def test_execute_post_commit_stages_filters_progress_for_narrow_callbacks() -> None:
    """Narrow progress callbacks should receive only supported keyword args."""

    progress_events: list[tuple[str, str | None]] = []

    def _record_progress(stage: str, status: str | None = None) -> None:
        progress_events.append((stage, status))

    execute_post_commit_stages(
        stages=[PostCommitStage(name="workloads", runner=lambda: {"count": 1})],
        info_logger_fn=lambda *_args, **_kwargs: None,
        stage_progress_callback=_record_progress,
        repo_count=1,
        run_id="run-456",
        monotonic_fn=SimpleNamespace(values=iter([1.0, 1.5])).__dict__["values"].__next__,
    )

    assert progress_events == [
        ("workloads", "started"),
        ("workloads", "completed"),
    ]


def test_execute_post_commit_stages_marks_skipped_stages_without_running() -> None:
    """Skipped stages should retain zero timing and never execute their runner."""

    calls: list[str] = []

    result = execute_post_commit_stages(
        stages=[PostCommitStage(name="inheritance", runner=lambda: calls.append("ran"))],
        skipped_stage_names={"inheritance"},
        info_logger_fn=lambda *_args, **_kwargs: None,
        monotonic_fn=SimpleNamespace(values=iter([1.0])).__dict__["values"].__next__,
    )

    assert calls == []
    assert result.stage_timings == {"inheritance": 0.0}
    assert result.stage_details == {}
