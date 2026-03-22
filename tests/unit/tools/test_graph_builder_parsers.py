from __future__ import annotations

import logging

from platform_context_graph.tools import graph_builder_parsers


def test_build_parser_registry_skips_unavailable_language(monkeypatch, caplog) -> None:
    """Service startup should degrade cleanly if one optional grammar is missing."""

    class FakeTreeSitterParser:
        def __init__(self, language_name: str) -> None:
            if language_name == "c_sharp":
                raise ValueError("Language 'c_sharp' is not available")
            self.language_name = language_name

    monkeypatch.setattr(graph_builder_parsers, "TreeSitterParser", FakeTreeSitterParser)
    caplog.set_level(logging.WARNING, logger=graph_builder_parsers.__name__)

    registry = graph_builder_parsers.build_parser_registry(lambda _key: "false")

    assert ".cs" not in registry
    assert registry[".py"].language_name == "python"
    assert (
        "Skipping parser for extension .cs because language c_sharp is unavailable"
        in caplog.text
    )


def test_build_parser_registry_keeps_available_language() -> None:
    """Known-good languages should still be registered normally."""

    registry = graph_builder_parsers.build_parser_registry(lambda _key: "false")

    assert ".py" in registry
    assert ".js" in registry


def test_build_parser_registry_uses_dedicated_tsx_parser() -> None:
    """TSX files should use the JSX-aware parser rather than plain TypeScript."""

    registry = graph_builder_parsers.build_parser_registry(lambda _key: "false")

    assert ".tsx" in registry
    assert (
        registry[".tsx"].language_specific_parser.__class__.__name__
        == "TypescriptJSXTreeSitterParser"
    )
