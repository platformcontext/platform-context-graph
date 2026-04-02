"""Unit tests for per-repository telemetry accumulator."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest


def _make_memory_sample(
    *, rss_bytes: int | None = None, cgroup_bytes: int | None = None
):
    """Build a minimal MemoryUsageSample-compatible object."""

    class _FakeSample:
        def __init__(self, rss, cgroup):
            self.rss_bytes = rss
            self.cgroup_memory_bytes = cgroup
            self.cgroup_memory_limit_bytes = None

    return _FakeSample(rss_bytes, cgroup_bytes)


class TestCreateRepoTelemetry:
    """Tests for the factory function."""

    def test_derives_repo_name_from_path(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
        )

        tel = create_repo_telemetry(Path("/home/user/repos/my-awesome-repo"))
        assert tel.repo_name == "my-awesome-repo"

    def test_stores_resolved_repo_path(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
        )

        tel = create_repo_telemetry(Path("/home/user/repos/some-repo"))
        assert tel.repo_path == str(Path("/home/user/repos/some-repo").resolve())

    def test_defaults_to_pending_status(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        assert tel.status == "pending"
        assert tel.error is None

    def test_defaults_all_timing_fields_none(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        assert tel.parse_duration_seconds is None
        assert tel.commit_duration_seconds is None
        assert tel.graph_write_duration_seconds is None
        assert tel.content_write_duration_seconds is None


class TestRecordMemorySample:
    """Tests for memory sample recording at lifecycle points."""

    def test_parse_start_records_rss(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
            record_memory_sample,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        sample = _make_memory_sample(rss_bytes=500 * 1024 * 1024)
        record_memory_sample(tel, "parse_start", sample)
        assert tel.rss_mib_parse_start == pytest.approx(500.0, abs=0.1)

    def test_parse_end_records_rss(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
            record_memory_sample,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        sample = _make_memory_sample(rss_bytes=600 * 1024 * 1024)
        record_memory_sample(tel, "parse_end", sample)
        assert tel.rss_mib_parse_end == pytest.approx(600.0, abs=0.1)

    def test_commit_start_records_rss_and_cgroup(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
            record_memory_sample,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        sample = _make_memory_sample(
            rss_bytes=700 * 1024 * 1024,
            cgroup_bytes=800 * 1024 * 1024,
        )
        record_memory_sample(tel, "commit_start", sample)
        assert tel.rss_mib_commit_start == pytest.approx(700.0, abs=0.1)
        assert tel.cgroup_memory_mib_commit_start == pytest.approx(800.0, abs=0.1)

    def test_commit_end_records_rss(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
            record_memory_sample,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        sample = _make_memory_sample(rss_bytes=900 * 1024 * 1024)
        record_memory_sample(tel, "commit_end", sample)
        assert tel.rss_mib_commit_end == pytest.approx(900.0, abs=0.1)

    def test_commit_batch_updates_peak_estimate(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
            record_memory_sample,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        record_memory_sample(
            tel, "commit_batch", _make_memory_sample(rss_bytes=500 * 1024 * 1024)
        )
        record_memory_sample(
            tel, "commit_batch", _make_memory_sample(rss_bytes=800 * 1024 * 1024)
        )
        record_memory_sample(
            tel, "commit_batch", _make_memory_sample(rss_bytes=600 * 1024 * 1024)
        )
        assert tel.rss_mib_commit_peak_estimate == pytest.approx(800.0, abs=0.1)

    def test_none_rss_leaves_field_unchanged(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
            record_memory_sample,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        sample = _make_memory_sample(rss_bytes=None)
        record_memory_sample(tel, "parse_start", sample)
        assert tel.rss_mib_parse_start is None

    def test_cgroup_parse_start_recorded(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
            record_memory_sample,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        sample = _make_memory_sample(
            rss_bytes=500 * 1024 * 1024,
            cgroup_bytes=600 * 1024 * 1024,
        )
        record_memory_sample(tel, "parse_start", sample)
        assert tel.cgroup_memory_mib_parse_start == pytest.approx(600.0, abs=0.1)


class TestRepoTelemetrySerialization:
    """Tests for JSON serialization compatibility."""

    def test_asdict_produces_json_serializable_output(self):
        import json

        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        tel.parse_duration_seconds = 1.5
        tel.status = "completed"
        result = asdict(tel)
        # Must not raise
        json_str = json.dumps(result)
        assert '"parse_duration_seconds": 1.5' in json_str

    def test_asdict_includes_all_timing_fields(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        result = asdict(tel)
        expected_keys = {
            "parse_queue_wait_seconds",
            "parse_duration_seconds",
            "commit_queue_wait_seconds",
            "commit_duration_seconds",
            "graph_write_duration_seconds",
            "content_write_duration_seconds",
            "checkpoint_duration_seconds",
            "total_repository_duration_seconds",
        }
        assert expected_keys.issubset(result.keys())

    def test_asdict_includes_memory_fields(self):
        from platform_context_graph.indexing.repo_telemetry import (
            create_repo_telemetry,
        )

        tel = create_repo_telemetry(Path("/tmp/repo"))
        result = asdict(tel)
        expected_keys = {
            "rss_mib_parse_start",
            "rss_mib_parse_end",
            "rss_mib_commit_start",
            "rss_mib_commit_end",
            "rss_mib_commit_peak_estimate",
        }
        assert expected_keys.issubset(result.keys())
