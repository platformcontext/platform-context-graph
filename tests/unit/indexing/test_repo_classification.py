"""Unit tests for repository classification for observability tagging."""

from __future__ import annotations

import pytest


class TestClassifyRepoPreParse:
    """Tests for pre-parse classification from file count signals."""

    def test_small_repo(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_pre_parse,
        )

        result = classify_repo_pre_parse(discovered_file_count=50)
        assert result == "small"

    def test_medium_repo(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_pre_parse,
        )

        result = classify_repo_pre_parse(discovered_file_count=500)
        assert result == "medium"

    def test_large_repo(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_pre_parse,
        )

        result = classify_repo_pre_parse(discovered_file_count=3000)
        assert result == "large"

    def test_xlarge_repo(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_pre_parse,
        )

        result = classify_repo_pre_parse(discovered_file_count=10000)
        assert result == "xlarge"

    def test_zero_files(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_pre_parse,
        )

        result = classify_repo_pre_parse(discovered_file_count=0)
        assert result == "small"

    def test_boundary_small_medium(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_pre_parse,
        )

        assert classify_repo_pre_parse(discovered_file_count=100) == "medium"
        assert classify_repo_pre_parse(discovered_file_count=99) == "small"

    def test_boundary_medium_large(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_pre_parse,
        )

        assert classify_repo_pre_parse(discovered_file_count=1000) == "large"
        assert classify_repo_pre_parse(discovered_file_count=999) == "medium"

    def test_boundary_large_xlarge(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_pre_parse,
        )

        assert classify_repo_pre_parse(discovered_file_count=5000) == "xlarge"
        assert classify_repo_pre_parse(discovered_file_count=4999) == "large"


class TestClassifyRepoRuntime:
    """Tests for runtime reclassification from observed signals."""

    def test_upgrade_from_medium_to_large(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_runtime,
        )

        result = classify_repo_runtime(
            pre_class="medium",
            parse_duration_seconds=120.0,
            parsed_file_count=800,
        )
        assert result == "large"

    def test_no_downgrade(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_runtime,
        )

        result = classify_repo_runtime(
            pre_class="large",
            parse_duration_seconds=1.0,
            parsed_file_count=10,
        )
        assert result == "large"

    def test_upgrade_by_entity_density(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_runtime,
        )

        result = classify_repo_runtime(
            pre_class="medium",
            parse_duration_seconds=60.0,
            parsed_file_count=500,
            entity_count=50000,
        )
        # High entity density (100 per file) should upgrade
        assert result in ("large", "xlarge")

    def test_stays_same_when_signals_normal(self):
        from platform_context_graph.indexing.repo_classification import (
            classify_repo_runtime,
        )

        result = classify_repo_runtime(
            pre_class="small",
            parse_duration_seconds=2.0,
            parsed_file_count=50,
        )
        assert result == "small"


class TestRepoClassOverrides:
    """Tests for operator-specified per-repo class overrides."""

    def test_env_override_applied(self, monkeypatch):
        from platform_context_graph.indexing.repo_classification import (
            load_repo_class_overrides,
        )

        monkeypatch.setenv(
            "PCG_REPO_CLASS_OVERRIDE",
            "boattrader-legacy:xlarge,bt-mobile:large",
        )
        overrides = load_repo_class_overrides()
        assert overrides["boattrader-legacy"] == "xlarge"
        assert overrides["bt-mobile"] == "large"

    def test_no_env_returns_empty(self, monkeypatch):
        from platform_context_graph.indexing.repo_classification import (
            load_repo_class_overrides,
        )

        monkeypatch.delenv("PCG_REPO_CLASS_OVERRIDE", raising=False)
        overrides = load_repo_class_overrides()
        assert overrides == {}

    def test_malformed_entry_skipped(self, monkeypatch):
        from platform_context_graph.indexing.repo_classification import (
            load_repo_class_overrides,
        )

        monkeypatch.setenv("PCG_REPO_CLASS_OVERRIDE", "good:large,bad,also:xlarge")
        overrides = load_repo_class_overrides()
        assert "good" in overrides
        assert "also" in overrides
        assert "bad" not in overrides
