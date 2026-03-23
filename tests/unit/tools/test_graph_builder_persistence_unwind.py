from __future__ import annotations

from platform_context_graph.tools import graph_builder_persistence_unwind


def test_entity_props_for_unwind_caps_oversized_value_preview(monkeypatch) -> None:
    """Oversized entity values should be truncated before they reach Neo4j."""

    monkeypatch.setattr(
        graph_builder_persistence_unwind,
        "get_config_value",
        lambda key: "10" if key == "PCG_MAX_ENTITY_VALUE_LENGTH" else None,
    )

    row = graph_builder_persistence_unwind.entity_props_for_unwind(
        "Variable",
        {
            "name": "buildConfig",
            "line_number": 12,
            "value": "abcdefghijklmnop",
            "source": "full source should stay intact",
            "docstring": "docs should stay intact",
        },
        "/tmp/example.js",
        False,
    )

    assert row["value"] == "abcdefghij [truncated]"
    assert row["source"] == "full source should stay intact"
    assert row["docstring"] == "docs should stay intact"


def test_entity_props_for_unwind_keeps_small_value_preview(monkeypatch) -> None:
    """Short entity values should pass through unchanged."""

    monkeypatch.setattr(
        graph_builder_persistence_unwind,
        "get_config_value",
        lambda key: "20" if key == "PCG_MAX_ENTITY_VALUE_LENGTH" else None,
    )

    row = graph_builder_persistence_unwind.entity_props_for_unwind(
        "Variable",
        {
            "name": "buildConfig",
            "line_number": 12,
            "value": "short-value",
        },
        "/tmp/example.js",
        False,
    )

    assert row["value"] == "short-value"
