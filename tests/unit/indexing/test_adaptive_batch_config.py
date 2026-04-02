"""Unit tests for class-aware adaptive batch configuration."""

from __future__ import annotations

import pytest


class TestAdaptiveBatchConfig:
    """Tests for repo-class-aware batch sizing."""

    def test_small_repo_gets_relaxed_file_batch(self):
        """Small repos should get a larger file batch size than default."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("small")
        assert config.file_batch_size > 50  # default is 50

    def test_medium_repo_gets_default_file_batch(self):
        """Medium repos should use the default file batch size."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("medium")
        assert config.file_batch_size == 50

    def test_large_repo_gets_default_or_equal_file_batch(self):
        """Large repos use medium-equivalent file batch to avoid batch overhead."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("large")
        assert config.file_batch_size <= 50

    def test_xlarge_repo_gets_reduced_file_batch(self):
        """XLarge repos should get a reduced file batch size."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("xlarge")
        assert config.file_batch_size < 50

    def test_dangerous_repo_gets_minimum_file_batch(self):
        """Dangerous repos should get the smallest safe file batch size."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("dangerous")
        assert config.file_batch_size <= 10

    def test_unknown_class_returns_medium_defaults(self):
        """Unknown repo class should fall back to medium defaults."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("unknown_class")
        medium = batch_config_for_class("medium")
        assert config.file_batch_size == medium.file_batch_size

    def test_none_class_returns_medium_defaults(self):
        """None repo class should fall back to medium defaults."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class(None)
        medium = batch_config_for_class("medium")
        assert config.file_batch_size == medium.file_batch_size


class TestAdaptiveFlushThreshold:
    """Tests for class-aware flush threshold."""

    def test_small_repo_has_relaxed_flush_threshold(self):
        """Small repos can accumulate more rows before flushing."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("small")
        assert config.flush_row_threshold >= 2000

    def test_large_repo_flushes_earlier(self):
        """Large repos should flush at a lower row count."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("large")
        assert config.flush_row_threshold < 2000

    def test_dangerous_repo_flushes_earliest(self):
        """Dangerous repos should flush at the lowest threshold."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("dangerous")
        small = batch_config_for_class("small")
        assert config.flush_row_threshold < small.flush_row_threshold


class TestAdaptiveEntityBatchSize:
    """Tests for class-aware Neo4j UNWIND batch size."""

    def test_small_repo_has_large_entity_batch(self):
        """Small repos can use large UNWIND batches."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("small")
        assert config.entity_batch_size >= 10000

    def test_xlarge_repo_has_reduced_entity_batch(self):
        """XLarge repos should use smaller UNWIND batches."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("xlarge")
        assert config.entity_batch_size < 10000

    def test_dangerous_repo_has_smallest_entity_batch(self):
        """Dangerous repos should use the smallest UNWIND batches."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("dangerous")
        assert config.entity_batch_size <= 2000


class TestAdaptiveTxFileLimit:
    """Tests for class-aware transaction file limit."""

    def test_small_repo_has_larger_tx_file_limit(self):
        """Small repos can process more files per transaction."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("small")
        assert config.tx_file_limit >= 5

    def test_xlarge_repo_has_reduced_tx_file_limit(self):
        """XLarge repos should process fewer files per transaction."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("xlarge")
        assert config.tx_file_limit < 5

    def test_dangerous_repo_has_minimum_tx_file_limit(self):
        """Dangerous repos should use 1 file per transaction."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("dangerous")
        assert config.tx_file_limit == 1


class TestAdaptiveContentBatchSize:
    """Tests for class-aware Postgres content upsert batch size."""

    def test_small_repo_has_large_content_batch(self):
        """Small repos can use larger Postgres batches."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("small")
        assert config.content_upsert_batch_size >= 500

    def test_xlarge_repo_has_reduced_content_batch(self):
        """XLarge repos should use smaller Postgres batches."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("xlarge")
        assert config.content_upsert_batch_size < 500

    def test_dangerous_repo_has_smallest_content_batch(self):
        """Dangerous repos should use the smallest Postgres batches."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("dangerous")
        assert config.content_upsert_batch_size <= 100


class TestBatchConfigDataclass:
    """Tests for AdaptiveBatchConfig structure."""

    def test_config_has_all_required_fields(self):
        """AdaptiveBatchConfig should expose all batch sizing knobs."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("medium")
        assert hasattr(config, "file_batch_size")
        assert hasattr(config, "flush_row_threshold")
        assert hasattr(config, "entity_batch_size")
        assert hasattr(config, "tx_file_limit")
        assert hasattr(config, "content_upsert_batch_size")
        assert hasattr(config, "repo_class")

    def test_config_records_repo_class(self):
        """Config should record which repo class it was generated for."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("large")
        assert config.repo_class == "large"

    def test_monotonic_decrease_file_batch(self):
        """File batch size should decrease monotonically from small to dangerous."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        classes = ["small", "medium", "large", "xlarge", "dangerous"]
        sizes = [batch_config_for_class(c).file_batch_size for c in classes]
        for i in range(len(sizes) - 1):
            assert (
                sizes[i] >= sizes[i + 1]
            ), f"{classes[i]}={sizes[i]} should be >= {classes[i+1]}={sizes[i+1]}"

    def test_monotonic_decrease_flush_threshold(self):
        """Flush threshold should decrease monotonically from small to dangerous."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        classes = ["small", "medium", "large", "xlarge", "dangerous"]
        sizes = [batch_config_for_class(c).flush_row_threshold for c in classes]
        for i in range(len(sizes) - 1):
            assert (
                sizes[i] >= sizes[i + 1]
            ), f"{classes[i]}={sizes[i]} should be >= {classes[i+1]}={sizes[i+1]}"


class TestAdaptiveBatchEnabled:
    """Tests for feature flag gating."""

    def test_disabled_returns_static_defaults(self, monkeypatch):
        """When adaptive batching is disabled, return static defaults."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            resolve_batch_config,
        )

        monkeypatch.setenv("PCG_ADAPTIVE_GRAPH_BATCHING_ENABLED", "false")
        config = resolve_batch_config(repo_class="xlarge")
        # Should return medium (default) config, ignoring xlarge
        assert config.file_batch_size == 50
        assert config.repo_class == "medium"

    def test_enabled_returns_class_aware_config(self, monkeypatch):
        """When adaptive batching is enabled, return class-aware config."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            resolve_batch_config,
        )

        monkeypatch.setenv("PCG_ADAPTIVE_GRAPH_BATCHING_ENABLED", "true")
        config = resolve_batch_config(repo_class="xlarge")
        assert config.file_batch_size < 50
        assert config.repo_class == "xlarge"

    def test_enabled_with_none_class_returns_medium(self, monkeypatch):
        """When enabled but no class provided, use medium defaults."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            resolve_batch_config,
        )

        monkeypatch.setenv("PCG_ADAPTIVE_GRAPH_BATCHING_ENABLED", "true")
        config = resolve_batch_config(repo_class=None)
        assert config.file_batch_size == 50
        assert config.repo_class == "medium"


class TestLargeXlargeBatchTuning:
    """Tests for tuned batch config values for large/xlarge repos."""

    def test_large_tx_file_limit_tuned(self):
        """Large repos should use tx_file_limit=5 after tuning."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("large")
        assert config.tx_file_limit == 5

    def test_xlarge_tx_file_limit_tuned(self):
        """XLarge repos should use tx_file_limit=4 after tuning."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("xlarge")
        assert config.tx_file_limit == 4

    def test_large_flush_row_threshold_tuned(self):
        """Large repos should use flush_row_threshold=1500 after tuning."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("large")
        assert config.flush_row_threshold == 1500

    def test_xlarge_flush_row_threshold_tuned(self):
        """XLarge repos should use flush_row_threshold=750 after tuning."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("xlarge")
        assert config.flush_row_threshold == 750

    def test_large_entity_batch_size_tuned(self):
        """Large repos should use entity_batch_size=7500 after tuning."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("large")
        assert config.entity_batch_size == 7_500

    def test_xlarge_entity_batch_size_tuned(self):
        """XLarge repos should use entity_batch_size=3500 after tuning."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("xlarge")
        assert config.entity_batch_size == 3_500

    def test_large_content_upsert_batch_size_tuned(self):
        """Large repos should use content_upsert_batch_size=350 after tuning."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("large")
        assert config.content_upsert_batch_size == 350

    def test_xlarge_content_upsert_batch_size_tuned(self):
        """XLarge repos should use content_upsert_batch_size=150 after tuning."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        config = batch_config_for_class("xlarge")
        assert config.content_upsert_batch_size == 150

    def test_tx_file_limit_monotonic_large_ge_xlarge(self):
        """tx_file_limit must be monotonically decreasing: large >= xlarge."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        large = batch_config_for_class("large")
        xlarge = batch_config_for_class("xlarge")
        assert large.tx_file_limit >= xlarge.tx_file_limit
