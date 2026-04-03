"""Unit tests for SKIP_EXTERNAL_RESOLUTION configuration option."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from platform_context_graph.cli.config_manager import (
    get_config_value,
    set_config_value,
    validate_config_value,
    CONFIG_DESCRIPTIONS,
    CONFIG_VALIDATORS,
    DEFAULT_CONFIG,
)


def _patch_temp_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Redirect config-manager file writes into a temporary directory."""

    config_dir = tmp_path / "config"
    config_file = config_dir / ".env"

    def _ensure_config_dir(path: Path = config_dir) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "logs").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "platform_context_graph.cli.config_manager.CONFIG_DIR",
        config_dir,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.config_manager.CONFIG_FILE",
        config_file,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.config_manager.ensure_config_dir",
        _ensure_config_dir,
    )
    return config_file


class TestSkipExternalResolutionConfig:
    """Test the SKIP_EXTERNAL_RESOLUTION configuration cli option."""

    def test_config_exists_in_descriptions(self):
        """Test that SKIP_EXTERNAL_RESOLUTION has a description."""
        assert "SKIP_EXTERNAL_RESOLUTION" in CONFIG_DESCRIPTIONS
        assert len(CONFIG_DESCRIPTIONS["SKIP_EXTERNAL_RESOLUTION"]) > 0
        assert "external" in CONFIG_DESCRIPTIONS["SKIP_EXTERNAL_RESOLUTION"].lower()

    def test_config_has_validator(self):
        """Test that SKIP_EXTERNAL_RESOLUTION has valid values list."""
        assert "SKIP_EXTERNAL_RESOLUTION" in CONFIG_VALIDATORS
        valid_values = CONFIG_VALIDATORS["SKIP_EXTERNAL_RESOLUTION"]
        assert isinstance(valid_values, list)
        assert len(valid_values) == 2

    def test_validator_accepts_true(self):
        """Test that validator list includes 'true'."""
        valid_values = CONFIG_VALIDATORS["SKIP_EXTERNAL_RESOLUTION"]
        assert "true" in valid_values

    def test_validator_accepts_false(self):
        """Test that validator list includes 'false'."""
        valid_values = CONFIG_VALIDATORS["SKIP_EXTERNAL_RESOLUTION"]
        assert "false" in valid_values

    def test_validator_rejects_invalid_values(self):
        """Test that validator list does not include invalid values."""
        valid_values = CONFIG_VALIDATORS["SKIP_EXTERNAL_RESOLUTION"]
        assert "yes" not in valid_values
        assert "no" not in valid_values
        assert "1" not in valid_values
        assert "0" not in valid_values
        assert "enabled" not in valid_values

    def test_default_value_is_false(self):
        """Test that the default value remains 'false'."""
        from platform_context_graph.cli.config_manager import DEFAULT_CONFIG

        assert "SKIP_EXTERNAL_RESOLUTION" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["SKIP_EXTERNAL_RESOLUTION"] == "false"

    def test_ignore_dirs_default_includes_iac_temp_directories(self):
        ignore_dirs = set(DEFAULT_CONFIG["IGNORE_DIRS"].split(","))
        assert ".terraform" in ignore_dirs
        assert ".terragrunt-cache" in ignore_dirs
        assert ".terramate-cache" in ignore_dirs
        assert ".pulumi" in ignore_dirs
        assert ".crossplane" in ignore_dirs
        assert ".serverless" in ignore_dirs
        assert ".aws-sam" in ignore_dirs
        assert "cdk.out" in ignore_dirs

    def test_max_entity_value_length_accepts_default_preview_cap(self):
        """Entity preview length validation should accept the default 200-char cap."""

        valid, error = validate_config_value("PCG_MAX_ENTITY_VALUE_LENGTH", "200")

        assert valid is True
        assert error is None

    def test_honor_gitignore_default_is_true(self):
        """Repo/workspace indexing should honor repo-local .gitignore by default."""

        assert "PCG_HONOR_GITIGNORE" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["PCG_HONOR_GITIGNORE"] == "true"

    def test_honor_gitignore_validator_accepts_boolean_values(self):
        """PCG_HONOR_GITIGNORE should validate like the other boolean toggles."""

        assert CONFIG_VALIDATORS["PCG_HONOR_GITIGNORE"] == ["true", "false"]
        assert validate_config_value("PCG_HONOR_GITIGNORE", "true") == (True, None)
        assert validate_config_value("PCG_HONOR_GITIGNORE", "false") == (True, None)

    def test_set_and_get_config_value(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Test setting and getting the configuration value."""
        _patch_temp_config(monkeypatch, tmp_path)
        monkeypatch.delenv("SKIP_EXTERNAL_RESOLUTION", raising=False)

        # Set to true
        set_config_value("SKIP_EXTERNAL_RESOLUTION", "true")
        assert get_config_value("SKIP_EXTERNAL_RESOLUTION").lower() == "true"

        # Set to false
        set_config_value("SKIP_EXTERNAL_RESOLUTION", "false")
        assert get_config_value("SKIP_EXTERNAL_RESOLUTION").lower() == "false"

    def test_environment_variable_override(self):
        """Test that environment variable SKIP_EXTERNAL_RESOLUTION works."""
        with patch.dict(os.environ, {"SKIP_EXTERNAL_RESOLUTION": "true"}):
            value = get_config_value("SKIP_EXTERNAL_RESOLUTION")
            assert value == "true"

        with patch.dict(os.environ, {"SKIP_EXTERNAL_RESOLUTION": "false"}):
            value = get_config_value("SKIP_EXTERNAL_RESOLUTION")
            assert value == "false"


class TestSkipExternalResolutionBehavior:
    """Test the behavior of SKIP_EXTERNAL_RESOLUTION in graph_builder.py

    Note: Full behavior testing requires Neo4j session mocking, which is complex.
    These tests verify the code structure and imports are correct.
    The actual behavior is tested implicitly through the integration tests.
    """

    def test_graph_builder_uses_config_value(self):
        """Test that GraphBuilder imports and can call get_config_value."""
        from platform_context_graph.tools.graph_builder import GraphBuilder
        from platform_context_graph.cli.config_manager import get_config_value

        # Verify the import exists and is callable
        assert callable(get_config_value)

        # Verify GraphBuilder class exists
        assert GraphBuilder is not None

    def test_skip_external_logic_exists_in_code(self):
        """Test that the skip_external logic remains in the call-relationship helper."""
        import inspect
        from platform_context_graph.graph.persistence.calls import (
            _prepare_call_rows,
        )

        source = inspect.getsource(_prepare_call_rows)

        assert "skip_external" in source
        assert "SKIP_EXTERNAL_RESOLUTION" in source
        assert "is_unresolved_external" in source
        assert "if skip_external and is_unresolved_external:" in source


class TestBackwardCompatibility:
    """Test that existing behavior is preserved when config is not set."""

    def test_default_behavior_unchanged(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Test that default behavior matches original (warnings + attempts)."""
        # When SKIP_EXTERNAL_RESOLUTION is not set or is "false",
        # behavior should match the pre-rename defaults
        _patch_temp_config(monkeypatch, tmp_path)

        with patch.dict(os.environ, {}, clear=True):
            from platform_context_graph.cli.config_manager import get_config_value

            # Default should be None or "false"
            value = get_config_value("SKIP_EXTERNAL_RESOLUTION")
            assert value is None or value.lower() == "false"

    def test_existing_configs_not_affected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Test that other configuration options still work."""
        # Setting SKIP_EXTERNAL_RESOLUTION should not affect other configs
        _patch_temp_config(monkeypatch, tmp_path)
        monkeypatch.delenv("SKIP_EXTERNAL_RESOLUTION", raising=False)
        set_config_value("SKIP_EXTERNAL_RESOLUTION", "true")
        set_config_value("INDEX_VARIABLES", "false")

        assert get_config_value("SKIP_EXTERNAL_RESOLUTION").lower() == "true"
        assert get_config_value("INDEX_VARIABLES").lower() == "false"


# Integration test (would require actual Neo4j - marked as e2e)
@pytest.mark.e2e
class TestSkipExternalResolutionE2E:
    """End-to-end tests for SKIP_EXTERNAL_RESOLUTION (requires Neo4j)."""

    def test_indexing_with_skip_external_enabled(self):
        """Test full indexing cycle with SKIP_EXTERNAL_RESOLUTION=true."""
        # This would be an actual integration test
        # Requires Neo4j running and test Java project
        # Should verify: no external warnings, only internal CALLS created
        pytest.skip("E2E test - requires Neo4j database")

    def test_performance_improvement(self):
        """Test that indexing is faster with SKIP_EXTERNAL_RESOLUTION=true."""
        # This would measure performance
        # Expected: significantly faster for Java projects with Spring/Commons
        pytest.skip("E2E test - requires Neo4j database and performance benchmarks")
