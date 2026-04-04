"""Unit tests for the V2 indexing metrics mixin."""

from __future__ import annotations

import pytest


class _FakeInstrument:
    """Capture calls to add() or record() for verification."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def add(self, value: int, attributes: dict | None = None) -> None:
        """Record an add call."""
        self.calls.append(("add", value, attributes or {}))

    def record(self, value: float, attributes: dict | None = None) -> None:
        """Record a record call."""
        self.calls.append(("record", value, attributes or {}))


class TestRecordRepoGraphWriteDuration:
    """Tests for per-repo graph write duration histogram."""

    def test_records_when_enabled(self):
        from platform_context_graph.observability.indexing_metrics_v2 import (
            RuntimeIndexMetricsV2Mixin,
        )

        mixin = _build_v2_mixin(enabled=True)
        mixin.index_repo_graph_write_duration = _FakeInstrument()
        mixin.record_repo_graph_write_duration(
            component="ingester",
            mode="full",
            source="cli",
            repo_class="large",
            duration_seconds=1.5,
        )
        assert len(mixin.index_repo_graph_write_duration.calls) == 1
        call = mixin.index_repo_graph_write_duration.calls[0]
        assert call[0] == "record"
        assert call[1] == 1.5
        assert call[2]["repo_class"] == "large"

    def test_noop_when_disabled(self):
        from platform_context_graph.observability.indexing_metrics_v2 import (
            RuntimeIndexMetricsV2Mixin,
        )

        mixin = _build_v2_mixin(enabled=False)
        mixin.index_repo_graph_write_duration = _FakeInstrument()
        mixin.record_repo_graph_write_duration(
            component="ingester",
            mode="full",
            source="cli",
            repo_class="large",
            duration_seconds=1.5,
        )
        assert len(mixin.index_repo_graph_write_duration.calls) == 0

    def test_noop_when_instrument_none(self):
        from platform_context_graph.observability.indexing_metrics_v2 import (
            RuntimeIndexMetricsV2Mixin,
        )

        mixin = _build_v2_mixin(enabled=True)
        mixin.index_repo_graph_write_duration = None
        # Should not raise
        mixin.record_repo_graph_write_duration(
            component="ingester",
            mode="full",
            source="cli",
            repo_class="large",
            duration_seconds=1.5,
        )


class TestRecordRepoContentWriteDuration:
    """Tests for per-repo content write duration histogram."""

    def test_records_when_enabled(self):
        from platform_context_graph.observability.indexing_metrics_v2 import (
            RuntimeIndexMetricsV2Mixin,
        )

        mixin = _build_v2_mixin(enabled=True)
        mixin.index_repo_content_write_duration = _FakeInstrument()
        mixin.record_repo_content_write_duration(
            component="ingester",
            mode="full",
            source="cli",
            repo_class="medium",
            duration_seconds=0.8,
        )
        assert len(mixin.index_repo_content_write_duration.calls) == 1
        call = mixin.index_repo_content_write_duration.calls[0]
        assert call[1] == 0.8
        assert call[2]["repo_class"] == "medium"


class TestRecordFallbackResolution:
    """Tests for fallback resolution counter."""

    def test_records_count(self):
        from platform_context_graph.observability.indexing_metrics_v2 import (
            RuntimeIndexMetricsV2Mixin,
        )

        mixin = _build_v2_mixin(enabled=True)
        mixin.index_fallback_resolution_total = _FakeInstrument()
        mixin.record_fallback_resolution(
            component="ingester",
            mode="full",
            source="cli",
            repo_class="small",
            count=42,
        )
        assert len(mixin.index_fallback_resolution_total.calls) == 1
        call = mixin.index_fallback_resolution_total.calls[0]
        assert call[0] == "add"
        assert call[1] == 42
        assert call[2]["repo_class"] == "small"


class TestRecordAmbiguousResolution:
    """Tests for ambiguous resolution counter."""

    def test_records_count(self):
        from platform_context_graph.observability.indexing_metrics_v2 import (
            RuntimeIndexMetricsV2Mixin,
        )

        mixin = _build_v2_mixin(enabled=True)
        mixin.index_ambiguous_resolution_total = _FakeInstrument()
        mixin.record_ambiguous_resolution(
            component="ingester",
            mode="full",
            source="cli",
            repo_class="xlarge",
            count=7,
        )
        assert len(mixin.index_ambiguous_resolution_total.calls) == 1
        call = mixin.index_ambiguous_resolution_total.calls[0]
        assert call[0] == "add"
        assert call[1] == 7
        assert call[2]["repo_class"] == "xlarge"


class TestRepoClassOnExistingMetrics:
    """Tests for repo_class parameter added to existing V1 methods."""

    def test_record_index_repository_duration_includes_repo_class(self):
        from platform_context_graph.observability.indexing_metrics_v2 import (
            RuntimeIndexMetricsV2Mixin,
        )

        mixin = _build_v2_mixin(enabled=True)
        mixin.index_repository_duration = _FakeInstrument()
        mixin.record_index_repository_duration(
            component="ingester",
            mode="full",
            source="cli",
            status="completed",
            duration_seconds=10.0,
            repo_class="large",
        )
        call = mixin.index_repository_duration.calls[0]
        assert call[2]["repo_class"] == "large"

    def test_record_index_repository_duration_omits_repo_class_when_none(self):
        from platform_context_graph.observability.indexing_metrics_v2 import (
            RuntimeIndexMetricsV2Mixin,
        )

        mixin = _build_v2_mixin(enabled=True)
        mixin.index_repository_duration = _FakeInstrument()
        mixin.record_index_repository_duration(
            component="ingester",
            mode="full",
            source="cli",
            status="completed",
            duration_seconds=10.0,
        )
        call = mixin.index_repository_duration.calls[0]
        assert "repo_class" not in call[2]

    def test_record_index_repositories_includes_repo_class(self):
        from platform_context_graph.observability.indexing_metrics_v2 import (
            RuntimeIndexMetricsV2Mixin,
        )

        mixin = _build_v2_mixin(enabled=True)
        mixin.index_repositories_total = _FakeInstrument()
        mixin.record_index_repositories(
            component="ingester",
            phase="commit",
            count=5,
            mode="full",
            source="cli",
            repo_class="medium",
        )
        call = mixin.index_repositories_total.calls[0]
        assert call[2]["repo_class"] == "medium"

    def test_record_index_stage_duration_includes_repo_class(self):
        from platform_context_graph.observability.indexing_metrics_v2 import (
            RuntimeIndexMetricsV2Mixin,
        )

        mixin = _build_v2_mixin(enabled=True)
        mixin.index_stage_duration = _FakeInstrument()
        mixin.record_index_stage_duration(
            component="ingester",
            mode="full",
            source="cli",
            stage="parse",
            duration_seconds=5.0,
            parse_strategy="async",
            parse_workers=4,
            repo_class="small",
        )
        call = mixin.index_stage_duration.calls[0]
        assert call[2]["repo_class"] == "small"

    def test_record_index_checkpoint_includes_repo_class(self):
        from platform_context_graph.observability.indexing_metrics_v2 import (
            RuntimeIndexMetricsV2Mixin,
        )

        mixin = _build_v2_mixin(enabled=True)
        mixin.index_checkpoints_total = _FakeInstrument()
        mixin.record_index_checkpoint(
            component="ingester",
            mode="full",
            source="cli",
            operation="save",
            status="completed",
            repo_class="xlarge",
        )
        call = mixin.index_checkpoints_total.calls[0]
        assert call[2]["repo_class"] == "xlarge"


def _build_v2_mixin(*, enabled: bool) -> object:
    """Build a minimal V2 mixin instance for testing."""
    from platform_context_graph.observability.indexing_metrics_v2 import (
        RuntimeIndexMetricsV2Mixin,
    )

    class _TestMixin(RuntimeIndexMetricsV2Mixin):
        pass

    obj = object.__new__(_TestMixin)
    obj.enabled = enabled
    # Set all V1 instrument attributes to None
    obj.index_repositories_total = None
    obj.index_checkpoints_total = None
    obj.index_repository_duration = None
    obj.index_stage_duration = None
    obj.index_lock_contention_skips_total = None
    # Set all V2 instrument attributes to None
    obj.index_repo_graph_write_duration = None
    obj.index_repo_content_write_duration = None
    obj.index_fallback_resolution_total = None
    obj.index_ambiguous_resolution_total = None
    return obj
