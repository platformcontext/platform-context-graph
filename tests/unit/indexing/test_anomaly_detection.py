"""Unit tests for anomaly threshold checking and event emission."""

from __future__ import annotations

from pathlib import Path

import pytest


def _make_telemetry(**kwargs):
    """Build a RepoTelemetry with specified overrides."""
    from platform_context_graph.indexing.repo_telemetry import RepoTelemetry

    defaults = {
        "repo_path": "/repos/test-repo",
        "repo_name": "test-repo",
    }
    defaults.update(kwargs)
    return RepoTelemetry(**defaults)


class TestCheckAnomalies:
    """Tests for threshold-based anomaly detection."""

    def test_parse_queue_wait_high(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            check_anomalies,
        )

        tel = _make_telemetry(parse_queue_wait_seconds=150.0)
        thresholds = AnomalyThresholds(parse_queue_wait_high_seconds=120.0)
        anomalies = check_anomalies(tel, thresholds)
        types = [a["type"] for a in anomalies]
        assert "parse_queue_wait_high" in types

    def test_commit_queue_wait_high(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            check_anomalies,
        )

        tel = _make_telemetry(commit_queue_wait_seconds=200.0)
        thresholds = AnomalyThresholds(commit_queue_wait_high_seconds=120.0)
        anomalies = check_anomalies(tel, thresholds)
        types = [a["type"] for a in anomalies]
        assert "commit_queue_wait_high" in types

    def test_commit_memory_high(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            check_anomalies,
        )

        tel = _make_telemetry(rss_mib_commit_end=3000.0)
        thresholds = AnomalyThresholds(repo_rss_high_mib=2048.0)
        anomalies = check_anomalies(tel, thresholds)
        types = [a["type"] for a in anomalies]
        assert "commit_memory_high" in types

    def test_graph_batch_rows_high(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            check_anomalies,
        )

        tel = _make_telemetry(max_graph_batch_rows=6000)
        thresholds = AnomalyThresholds(graph_batch_rows_high=5000)
        anomalies = check_anomalies(tel, thresholds)
        types = [a["type"] for a in anomalies]
        assert "graph_batch_rows_high" in types

    def test_content_batch_rows_high(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            check_anomalies,
        )

        tel = _make_telemetry(max_content_batch_rows=6000)
        thresholds = AnomalyThresholds(content_batch_rows_high=5000)
        anomalies = check_anomalies(tel, thresholds)
        types = [a["type"] for a in anomalies]
        assert "content_batch_rows_high" in types

    def test_duration_high(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            check_anomalies,
        )

        tel = _make_telemetry(commit_duration_seconds=400.0)
        thresholds = AnomalyThresholds(commit_duration_high_seconds=300.0)
        anomalies = check_anomalies(tel, thresholds)
        types = [a["type"] for a in anomalies]
        assert "duration_high" in types

    def test_fallback_resolution_high(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            check_anomalies,
        )

        tel = _make_telemetry(fallback_resolution_attempts=600)
        thresholds = AnomalyThresholds(fallback_resolution_high_count=500)
        anomalies = check_anomalies(tel, thresholds)
        types = [a["type"] for a in anomalies]
        assert "fallback_resolution_high" in types

    def test_graph_lookup_high(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            check_anomalies,
        )

        tel = _make_telemetry(hot_graph_lookup_count=1200)
        thresholds = AnomalyThresholds(graph_lookup_high_count=1000)
        anomalies = check_anomalies(tel, thresholds)
        types = [a["type"] for a in anomalies]
        assert "graph_lookup_high" in types

    def test_no_anomalies_below_thresholds(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            check_anomalies,
        )

        tel = _make_telemetry(
            parse_queue_wait_seconds=10.0,
            commit_queue_wait_seconds=5.0,
            commit_duration_seconds=30.0,
            rss_mib_commit_end=500.0,
            max_graph_batch_rows=100,
            max_content_batch_rows=100,
            fallback_resolution_attempts=10,
            hot_graph_lookup_count=50,
        )
        thresholds = AnomalyThresholds()
        anomalies = check_anomalies(tel, thresholds)
        assert anomalies == []

    def test_anomaly_includes_actual_and_threshold(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            check_anomalies,
        )

        tel = _make_telemetry(parse_queue_wait_seconds=150.0)
        thresholds = AnomalyThresholds(parse_queue_wait_high_seconds=120.0)
        anomalies = check_anomalies(tel, thresholds)
        anomaly = next(a for a in anomalies if a["type"] == "parse_queue_wait_high")
        assert anomaly["actual"] == 150.0
        assert anomaly["threshold"] == 120.0
        assert anomaly["repo_name"] == "test-repo"

    def test_none_values_do_not_trigger(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            check_anomalies,
        )

        tel = _make_telemetry()  # All None timing fields
        thresholds = AnomalyThresholds()
        anomalies = check_anomalies(tel, thresholds)
        assert anomalies == []


class TestLoadAnomalyThresholds:
    """Tests for threshold loading from environment."""

    def test_defaults(self):
        from platform_context_graph.indexing.anomaly_detection import (
            load_anomaly_thresholds,
        )

        thresholds = load_anomaly_thresholds()
        assert thresholds.parse_queue_wait_high_seconds == 120.0
        assert thresholds.repo_rss_high_mib == 2048.0

    def test_env_override(self, monkeypatch):
        from platform_context_graph.indexing.anomaly_detection import (
            load_anomaly_thresholds,
        )

        monkeypatch.setenv("PCG_ANOMALY_PARSE_QUEUE_WAIT_HIGH_SECONDS", "60.0")
        thresholds = load_anomaly_thresholds()
        assert thresholds.parse_queue_wait_high_seconds == 60.0


class TestClassAdjustedThresholds:
    """Tests for class-aware threshold adjustment."""

    def test_xlarge_gets_looser_thresholds(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            class_adjusted_thresholds,
        )

        base = AnomalyThresholds(commit_duration_high_seconds=300.0)
        adjusted = class_adjusted_thresholds(base, "xlarge")
        assert adjusted.commit_duration_high_seconds > 300.0

    def test_small_gets_tighter_thresholds(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            class_adjusted_thresholds,
        )

        base = AnomalyThresholds(commit_duration_high_seconds=300.0)
        adjusted = class_adjusted_thresholds(base, "small")
        assert adjusted.commit_duration_high_seconds < 300.0

    def test_medium_unchanged(self):
        from platform_context_graph.indexing.anomaly_detection import (
            AnomalyThresholds,
            class_adjusted_thresholds,
        )

        base = AnomalyThresholds()
        adjusted = class_adjusted_thresholds(base, "medium")
        assert adjusted == base


class TestEmitAnomalyEvents:
    """Tests for anomaly event emission."""

    def test_calls_warning_logger(self):
        from platform_context_graph.indexing.anomaly_detection import (
            emit_anomaly_events,
        )

        calls = []
        anomalies = [
            {
                "type": "parse_queue_wait_high",
                "actual": 150.0,
                "threshold": 120.0,
                "repo_name": "test-repo",
                "repo_path": "/repos/test-repo",
            }
        ]
        emit_anomaly_events(
            anomalies,
            warning_logger_fn=lambda msg, **kw: calls.append((msg, kw)),
            run_id="run123",
        )
        assert len(calls) == 1
        assert "parse_queue_wait_high" in calls[0][0]
