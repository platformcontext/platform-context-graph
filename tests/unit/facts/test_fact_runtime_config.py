"""Tests for facts-first runtime configuration metadata."""

from __future__ import annotations

from platform_context_graph.cli.config_catalog import CONFIG_DESCRIPTIONS
from platform_context_graph.cli.config_catalog import DEFAULT_CONFIG


def test_config_catalog_exposes_fact_pool_defaults() -> None:
    """Facts-first pool sizing should be visible in default config."""

    assert DEFAULT_CONFIG["PCG_FACT_STORE_POOL_MAX_SIZE"] == "4"
    assert DEFAULT_CONFIG["PCG_FACT_QUEUE_POOL_MAX_SIZE"] == "4"


def test_config_catalog_describes_fact_pool_settings() -> None:
    """Facts-first pool sizing should be documented for operators."""

    assert "PCG_FACT_STORE_POOL_MAX_SIZE" in CONFIG_DESCRIPTIONS
    assert "PCG_FACT_QUEUE_POOL_MAX_SIZE" in CONFIG_DESCRIPTIONS
    assert "pool" in CONFIG_DESCRIPTIONS["PCG_FACT_STORE_POOL_MAX_SIZE"].lower()
    assert "pool" in CONFIG_DESCRIPTIONS["PCG_FACT_QUEUE_POOL_MAX_SIZE"].lower()
