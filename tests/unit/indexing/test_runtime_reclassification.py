"""Tests for runtime reclassification wire-up in coordinator pipeline."""

from __future__ import annotations

import inspect

import pytest


class TestPipelineImportsRuntimeClassifier:
    """Verify the pipeline module imports and can call classify_repo_runtime."""

    def test_coordinator_pipeline_imports_classify_repo_runtime(self):
        """coordinator_pipeline should import classify_repo_runtime."""
        from platform_context_graph.indexing import coordinator_pipeline

        assert hasattr(coordinator_pipeline, "classify_repo_runtime")

    def test_classify_repo_runtime_callable(self):
        """classify_repo_runtime should be callable from the pipeline module."""
        from platform_context_graph.indexing.coordinator_pipeline import (
            classify_repo_runtime,
        )

        assert callable(classify_repo_runtime)


class TestRuntimeReclassificationUpgradeOnly:
    """Verify runtime reclassification only upgrades, never downgrades."""

    def test_medium_repo_with_long_parse_upgrades_to_large(self):
        """A medium repo that takes >60s to parse should upgrade to large."""
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_runtime,
        )

        result = classify_repo_runtime(
            pre_class="medium",
            parse_duration_seconds=90.0,
            parsed_file_count=800,
        )
        assert result == "large"

    def test_medium_repo_with_very_long_parse_upgrades_to_xlarge(self):
        """A medium repo that takes >300s to parse should upgrade to xlarge."""
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_runtime,
        )

        result = classify_repo_runtime(
            pre_class="medium",
            parse_duration_seconds=350.0,
            parsed_file_count=800,
        )
        assert result == "xlarge"

    def test_large_repo_never_downgrades_to_medium(self):
        """A large repo with fast parse should stay large, not downgrade."""
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_runtime,
        )

        result = classify_repo_runtime(
            pre_class="large",
            parse_duration_seconds=5.0,
            parsed_file_count=2000,
        )
        assert result == "large"

    def test_high_entity_density_upgrades_class(self):
        """Entity density >100/file should push to xlarge."""
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_runtime,
        )

        result = classify_repo_runtime(
            pre_class="medium",
            parse_duration_seconds=30.0,
            parsed_file_count=500,
            entity_count=60000,
        )
        assert result == "xlarge"


class TestSnapshotEntityCounting:
    """Verify entity counting from snapshot file_data for reclassification."""

    def test_count_entities_from_file_data(self):
        """Should count total entities across all entity-bearing fields."""
        from platform_context_graph.indexing.coordinator_pipeline import (
            _count_snapshot_entities,
        )

        file_data = [
            {
                "path": "/repo/a.py",
                "functions": [{"name": "foo"}, {"name": "bar"}],
                "classes": [{"name": "MyClass"}],
                "variables": [],
            },
            {
                "path": "/repo/b.py",
                "functions": [{"name": "baz"}],
                "classes": [],
            },
        ]
        assert _count_snapshot_entities(file_data) == 4

    def test_count_entities_empty_file_data(self):
        """Empty file_data should return 0."""
        from platform_context_graph.indexing.coordinator_pipeline import (
            _count_snapshot_entities,
        )

        assert _count_snapshot_entities([]) == 0

    def test_count_entities_no_entity_fields(self):
        """Files with no entity fields should contribute 0."""
        from platform_context_graph.indexing.coordinator_pipeline import (
            _count_snapshot_entities,
        )

        file_data = [{"path": "/repo/config.yaml"}]
        assert _count_snapshot_entities(file_data) == 0
