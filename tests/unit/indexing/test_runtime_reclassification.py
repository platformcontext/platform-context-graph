"""Tests for runtime reclassification rules."""

from __future__ import annotations


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
