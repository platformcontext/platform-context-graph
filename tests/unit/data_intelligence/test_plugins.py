"""Unit tests for vendor-neutral data-intelligence plugin registration."""

from __future__ import annotations

import pytest

from platform_context_graph.data_intelligence.plugins import (
    DataIntelligencePlugin,
    DataIntelligenceRegistry,
)


class _ReplayPlugin:
    """Minimal test plugin implementing the public plugin protocol."""

    name = "warehouse-replay"
    category = "warehouse"
    replay_fixture_groups = ("warehouse_replay_comprehensive",)

    def normalize(self, payload):
        return payload


def test_registry_registers_and_lists_plugins() -> None:
    """The registry should store plugins in stable registration order."""

    registry = DataIntelligenceRegistry()
    registry.register(_ReplayPlugin())

    plugins = registry.list_plugins()

    assert [plugin.name for plugin in plugins] == ["warehouse-replay"]
    assert isinstance(plugins[0], DataIntelligencePlugin)
    assert plugins[0].category == "warehouse"
    assert plugins[0].replay_fixture_groups == ("warehouse_replay_comprehensive",)


class _BIReplayPlugin:
    """Minimal BI replay plugin implementing the public plugin protocol."""

    name = "bi-replay"
    category = "bi"
    replay_fixture_groups = ("bi_replay_comprehensive",)

    def normalize(self, payload):
        return payload


def test_registry_supports_bi_category_plugins() -> None:
    """The registry should keep BI adapters alongside warehouse adapters."""

    registry = DataIntelligenceRegistry()
    registry.register(_ReplayPlugin())
    registry.register(_BIReplayPlugin())

    plugins = registry.list_plugins()

    assert [plugin.name for plugin in plugins] == ["warehouse-replay", "bi-replay"]
    assert plugins[1].category == "bi"


class _SemanticReplayPlugin:
    """Minimal semantic replay plugin implementing the public plugin protocol."""

    name = "semantic-replay"
    category = "semantic"
    replay_fixture_groups = ("semantic_replay_comprehensive",)

    def normalize(self, payload):
        return payload


def test_registry_supports_semantic_category_plugins() -> None:
    """The registry should keep semantic adapters alongside other plugin types."""

    registry = DataIntelligenceRegistry()
    registry.register(_ReplayPlugin())
    registry.register(_BIReplayPlugin())
    registry.register(_SemanticReplayPlugin())

    plugins = registry.list_plugins()

    assert [plugin.name for plugin in plugins] == [
        "warehouse-replay",
        "bi-replay",
        "semantic-replay",
    ]
    assert plugins[2].category == "semantic"


class _QualityReplayPlugin:
    """Minimal quality replay plugin implementing the public plugin protocol."""

    name = "quality-replay"
    category = "quality"
    replay_fixture_groups = ("quality_replay_comprehensive",)

    def normalize(self, payload):
        return payload


def test_registry_supports_quality_category_plugins() -> None:
    """The registry should keep quality adapters alongside other plugin types."""

    registry = DataIntelligenceRegistry()
    registry.register(_ReplayPlugin())
    registry.register(_BIReplayPlugin())
    registry.register(_SemanticReplayPlugin())
    registry.register(_QualityReplayPlugin())

    plugins = registry.list_plugins()

    assert [plugin.name for plugin in plugins] == [
        "warehouse-replay",
        "bi-replay",
        "semantic-replay",
        "quality-replay",
    ]
    assert plugins[3].category == "quality"


def test_registry_rejects_duplicate_plugin_names() -> None:
    """The registry should fail fast when names collide."""

    registry = DataIntelligenceRegistry()
    registry.register(_ReplayPlugin())

    with pytest.raises(ValueError, match="warehouse-replay"):
        registry.register(_ReplayPlugin())
