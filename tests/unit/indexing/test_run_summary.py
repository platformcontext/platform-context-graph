"""Unit tests for the run summary artifact builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_repo_telemetry(
    repo_name: str,
    *,
    parse_duration: float = 1.0,
    commit_duration: float = 2.0,
    parse_queue_wait: float = 0.5,
    commit_queue_wait: float = 0.3,
    graph_write_duration: float = 1.5,
    content_write_duration: float = 0.5,
    parsed_file_count: int = 100,
    rss_mib_commit_end: float = 500.0,
    status: str = "completed",
    repo_class: str | None = None,
    anomalies: list | None = None,
):
    """Build a minimal RepoTelemetry for summary testing."""
    from platform_context_graph.indexing.repo_telemetry import RepoTelemetry

    return RepoTelemetry(
        repo_path=f"/repos/{repo_name}",
        repo_name=repo_name,
        parse_duration_seconds=parse_duration,
        commit_duration_seconds=commit_duration,
        parse_queue_wait_seconds=parse_queue_wait,
        commit_queue_wait_seconds=commit_queue_wait,
        graph_write_duration_seconds=graph_write_duration,
        content_write_duration_seconds=content_write_duration,
        parsed_file_count=parsed_file_count,
        rss_mib_commit_end=rss_mib_commit_end,
        status=status,
        repo_class=repo_class,
        anomalies=anomalies or [],
    )


def _make_run_state(
    *,
    run_id: str = "abc123",
    root_path: str = "/repos",
    status: str = "completed",
    finalization_status: str = "completed",
    stage_durations: dict | None = None,
    repos: dict | None = None,
):
    """Build a minimal IndexRunState-compatible object."""
    from types import SimpleNamespace

    run = SimpleNamespace(
        run_id=run_id,
        root_path=root_path,
        status=status,
        finalization_status=finalization_status,
        finalization_stage_durations=stage_durations or {},
        finalization_stage_details={},
        repositories=repos or {},
    )
    run.completed_repositories = lambda: sum(
        1 for r in run.repositories.values() if getattr(r, "status", "") == "completed"
    )
    run.failed_repositories = lambda: sum(
        1 for r in run.repositories.values() if getattr(r, "status", "") == "failed"
    )
    return run


def _make_config(**overrides):
    """Build a RunSummaryConfig with defaults."""
    from platform_context_graph.indexing.run_summary import RunSummaryConfig

    defaults = {
        "parse_workers": 4,
        "commit_workers": 1,
        "queue_depth": 8,
        "file_batch_size": 50,
        "max_calls_per_file": 50,
        "call_resolution_scope": "repo",
        "index_variables": False,
        "parse_multiprocess": False,
    }
    defaults.update(overrides)
    return RunSummaryConfig(**defaults)


class TestComputeTimingDistributions:
    """Tests for percentile calculation over repo telemetries."""

    def test_known_values_p50_p95_p99_max(self):
        from platform_context_graph.indexing.run_summary import (
            compute_timing_distributions,
        )

        telemetries = [
            _make_repo_telemetry(f"repo-{i}", parse_duration=float(i))
            for i in range(1, 101)
        ]
        result = compute_timing_distributions(telemetries)
        assert result["parse_duration_seconds"]["max"] == 100.0
        assert result["parse_duration_seconds"]["p50"] == pytest.approx(50.0, abs=1.0)
        assert result["parse_duration_seconds"]["p95"] == pytest.approx(95.0, abs=1.0)
        assert result["parse_duration_seconds"]["p99"] == pytest.approx(99.0, abs=1.0)

    def test_single_repo(self):
        from platform_context_graph.indexing.run_summary import (
            compute_timing_distributions,
        )

        telemetries = [_make_repo_telemetry("solo", parse_duration=42.0)]
        result = compute_timing_distributions(telemetries)
        assert result["parse_duration_seconds"]["p50"] == 42.0
        assert result["parse_duration_seconds"]["max"] == 42.0

    def test_empty_returns_zeros(self):
        from platform_context_graph.indexing.run_summary import (
            compute_timing_distributions,
        )

        result = compute_timing_distributions([])
        assert result["parse_duration_seconds"]["p50"] == 0.0
        assert result["parse_duration_seconds"]["max"] == 0.0


class TestComputeOutliers:
    """Tests for top-N outlier extraction."""

    def test_returns_top_5_by_default(self):
        from platform_context_graph.indexing.run_summary import compute_outliers

        telemetries = [
            _make_repo_telemetry(f"repo-{i}", parse_duration=float(i))
            for i in range(1, 21)
        ]
        result = compute_outliers(telemetries)
        top_parse = result["top_parse_duration"]
        assert len(top_parse) == 5
        assert top_parse[0]["value"] == 20.0
        assert top_parse[0]["repo_name"] == "repo-20"

    def test_custom_top_n(self):
        from platform_context_graph.indexing.run_summary import compute_outliers

        telemetries = [
            _make_repo_telemetry(f"repo-{i}", parse_duration=float(i))
            for i in range(1, 11)
        ]
        result = compute_outliers(telemetries, top_n=3)
        assert len(result["top_parse_duration"]) == 3

    def test_fewer_repos_than_top_n(self):
        from platform_context_graph.indexing.run_summary import compute_outliers

        telemetries = [_make_repo_telemetry("only-one", parse_duration=5.0)]
        result = compute_outliers(telemetries, top_n=5)
        assert len(result["top_parse_duration"]) == 1


class TestBuildRunSummary:
    """Tests for the full summary artifact builder."""

    def test_schema_version(self):
        from platform_context_graph.indexing.run_summary import build_run_summary

        summary = build_run_summary(
            run_state=_make_run_state(),
            repo_telemetry_map={},
            config=_make_config(),
            started_at="2026-04-01T00:00:00Z",
            finished_at="2026-04-01T01:00:00Z",
        )
        assert summary["schema_version"] == "1.0"

    def test_per_repository_has_expected_fields(self):
        from platform_context_graph.indexing.run_summary import build_run_summary

        tel = _make_repo_telemetry("my-repo")
        summary = build_run_summary(
            run_state=_make_run_state(),
            repo_telemetry_map={"/repos/my-repo": tel},
            config=_make_config(),
            started_at="2026-04-01T00:00:00Z",
            finished_at="2026-04-01T01:00:00Z",
        )
        repos = summary["per_repository"]
        assert len(repos) == 1
        repo = repos[0]
        assert repo["repo_name"] == "my-repo"
        assert repo["parse_duration_seconds"] == 1.0
        assert repo["commit_duration_seconds"] == 2.0
        assert repo["status"] == "completed"

    def test_config_snapshot_captured(self):
        from platform_context_graph.indexing.run_summary import build_run_summary

        summary = build_run_summary(
            run_state=_make_run_state(),
            repo_telemetry_map={},
            config=_make_config(parse_workers=8),
            started_at="2026-04-01T00:00:00Z",
            finished_at="2026-04-01T01:00:00Z",
        )
        assert summary["config"]["parse_workers"] == 8

    def test_finalization_rollups(self):
        from platform_context_graph.indexing.run_summary import build_run_summary

        stage_durations = {
            "inheritance": 10.0,
            "function_calls": 20.0,
            "infra_links": 5.0,
            "workloads": 3.0,
            "relationship_resolution": 2.0,
        }
        summary = build_run_summary(
            run_state=_make_run_state(stage_durations=stage_durations),
            repo_telemetry_map={},
            config=_make_config(),
            started_at="2026-04-01T00:00:00Z",
            finished_at="2026-04-01T01:00:00Z",
        )
        rollups = summary["finalization"]["provisional_rollups"]
        assert rollups["resolution_duration_seconds"] == pytest.approx(30.0)
        assert rollups["evidence_promotion_duration_seconds"] == pytest.approx(10.0)

    def test_anomaly_counts_aggregated(self):
        from platform_context_graph.indexing.run_summary import build_run_summary

        tel = _make_repo_telemetry(
            "my-repo",
            anomalies=[
                {"type": "parse_queue_wait_high"},
                {"type": "commit_memory_high"},
            ],
        )
        summary = build_run_summary(
            run_state=_make_run_state(),
            repo_telemetry_map={"/repos/my-repo": tel},
            config=_make_config(),
            started_at="2026-04-01T00:00:00Z",
            finished_at="2026-04-01T01:00:00Z",
        )
        assert summary["anomalies"]["total_count"] == 2
        assert summary["anomalies"]["by_type"]["parse_queue_wait_high"] == 1
        assert summary["anomalies"]["by_type"]["commit_memory_high"] == 1

    def test_totals_counts(self):
        from platform_context_graph.indexing.run_summary import build_run_summary

        tels = {
            f"/repos/repo-{i}": _make_repo_telemetry(
                f"repo-{i}", parsed_file_count=10 * i
            )
            for i in range(1, 4)
        }
        summary = build_run_summary(
            run_state=_make_run_state(),
            repo_telemetry_map=tels,
            config=_make_config(),
            started_at="2026-04-01T00:00:00Z",
            finished_at="2026-04-01T01:00:00Z",
        )
        assert summary["totals"]["repositories_discovered"] == 3
        assert summary["totals"]["total_files_parsed"] == 60

    def test_output_is_json_serializable(self):
        from platform_context_graph.indexing.run_summary import build_run_summary

        tel = _make_repo_telemetry("test-repo")
        summary = build_run_summary(
            run_state=_make_run_state(),
            repo_telemetry_map={"/repos/test-repo": tel},
            config=_make_config(),
            started_at="2026-04-01T00:00:00Z",
            finished_at="2026-04-01T01:00:00Z",
        )
        # Must not raise
        json.dumps(summary)


class TestWriteRunSummary:
    """Tests for summary artifact file I/O."""

    def test_writes_valid_json(self, tmp_path):
        from platform_context_graph.indexing.run_summary import write_run_summary

        summary = {"schema_version": "1.0", "run_id": "test123"}
        path = write_run_summary(summary, run_id="test123", output_dir=tmp_path)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["schema_version"] == "1.0"

    def test_filename_contains_run_id(self, tmp_path):
        from platform_context_graph.indexing.run_summary import write_run_summary

        summary = {"run_id": "abc456"}
        path = write_run_summary(summary, run_id="abc456", output_dir=tmp_path)
        assert "abc456" in path.name


class TestSummaryOutputDir:
    """Tests for output directory resolution."""

    def test_env_override(self, monkeypatch, tmp_path):
        from platform_context_graph.indexing.run_summary import summary_output_dir

        monkeypatch.setenv("PCG_INDEX_SUMMARY_DIR", str(tmp_path))
        result = summary_output_dir("run123")
        assert result == tmp_path

    def test_default_under_app_home(self, monkeypatch):
        from platform_context_graph.indexing.run_summary import summary_output_dir

        monkeypatch.delenv("PCG_INDEX_SUMMARY_DIR", raising=False)
        result = summary_output_dir("run123")
        assert "run123" in str(result)
